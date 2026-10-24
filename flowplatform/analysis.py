"""FCS loading, gating and plotting helpers."""
import logging

import matplotlib
matplotlib.use('Agg')

import flowkit as fk
import matplotlib.path as mpl_path
import matplotlib.pyplot as plt
import numpy as np
from flowutils import transforms
from matplotlib.colors import LogNorm
from matplotlib.patches import Polygon

log = logging.getLogger(__name__)

SCATTER_CHANNELS = ['FSC-A', 'FSC-H', 'FSC-W', 'SSC-A', 'SSC-H', 'SSC-W']

# Logicle parameters shared by sample transforms and gate/tick conversion.
LOGICLE = dict(t=262144, w=0.5, m=4.5, a=0)
ARCSINH_COFACTOR = 150

SCALES = ('linear', 'logicle', 'arcsinh')

TICKS_LINEAR = [-10000, -1000, -100, 0, 100, 1000, 10000, 100000]
TICKS_LABELS = ['$-10^{4}$', '$-10^{3}$', '$-10^{2}$', '0', '$10^{2}$', '$10^{3}$', '$10^{4}$', '$10^{5}$']

# Plot area as fractions of the figure (left, bottom, right, top). Fixed so the
# browser can map mouse positions on the image back to data coordinates.
PLOT_AXES = (0.13, 0.11, 0.97, 0.97)


def channel_names(panel):
    return SCATTER_CHANNELS + [ch['ch_name'] for ch in panel['channels'] if ch.get('active') == 1]


def fluoro_name(panel, ch_name):
    if ch_name in SCATTER_CHANNELS:
        return ch_name
    for ch in panel['channels']:
        if ch['ch_name'] == ch_name:
            return ch['fluoro_name']
    raise ValueError(f'Unknown channel: {ch_name}')


def _logicle_transform():
    p = LOGICLE
    return fk.transforms.LogicleTransform(param_t=p['t'], param_w=p['w'], param_m=p['m'], param_a=p['a'])


def to_logicle(values):
    arr = np.asarray(values, dtype=float).reshape(-1, 1)
    return transforms.logicle(arr, [0], **LOGICLE).ravel()


def load_sample(sample_path):
    """Load one FCS file; returns (raw, logicle) event dataframes."""
    sample = fk.Sample(sample_path)
    sample.apply_transform(_logicle_transform())
    return (sample.as_dataframe(source='raw', subsample=False),
            sample.as_dataframe(source='xform', subsample=False))


def channel_values(frames, panel, ch, scale):
    df = frames[1] if scale == 'logicle' else frames[0]
    values = np.asarray(df[fluoro_name(panel, ch)]).squeeze().astype(float)
    return np.arcsinh(values / ARCSINH_COFACTOR) if scale == 'arcsinh' else values


def load_channel_pair(sample_path, panel, ch_x, ch_y, x_scale, y_scale):
    frames = load_sample(sample_path)
    return channel_values(frames, panel, ch_x, x_scale), channel_values(frames, panel, ch_y, y_scale)


def from_logicle(values):
    arr = np.asarray(values, dtype=float).reshape(-1, 1)
    return transforms.logicle_inverse(arr, [0], **LOGICLE).ravel()


def to_scale(values, scale):
    """Convert linear values to the given axis scale."""
    if scale == 'logicle':
        return to_logicle(values)
    if scale == 'arcsinh':
        return np.arcsinh(np.asarray(values, dtype=float) / ARCSINH_COFACTOR)
    return np.asarray(values, dtype=float)


def native_scale(ch_name):
    """Scale a gate on this channel was drawn in: scatter gates are linear, fluorescence gates logicle."""
    return 'linear' if ch_name in SCATTER_CHANNELS else 'logicle'


def gate_polygon(gate, x_scale, y_scale):
    """Gate vertices converted to the requested axis scales.

    In the panel config, scatter-channel coordinates are raw linear values while
    fluorescence-channel coordinates are logicle values multiplied by t (262144).
    """
    pts = gate_vertices(gate['coords'])
    for axis, ch, scale in ((0, gate['ch_X'], x_scale), (1, gate['ch_Y'], y_scale)):
        values = pts[:, axis]
        if native_scale(ch) == 'logicle':
            values = values / LOGICLE['t']
            if scale == 'logicle':
                pts[:, axis] = values
                continue
            values = from_logicle(values)
        pts[:, axis] = to_scale(values, scale)
    return pts


def gate_vertices(coords, x_scale='linear', y_scale='linear'):
    """Normalise polygon coordinates (list of pairs or {'x','y'} dicts, in linear units) to the plot scales."""
    pts = np.array([[float(c['x']), float(c['y'])] if isinstance(c, dict) else [float(c[0]), float(c[1])]
                    for c in coords])
    pts[:, 0] = to_scale(pts[:, 0], x_scale)
    pts[:, 1] = to_scale(pts[:, 1], y_scale)
    return pts


def count_in_polygon(x, y, vertices):
    path = mpl_path.Path(vertices)
    return int(np.sum(path.contains_points(np.column_stack((x, y)))))


def point_density(x, y, bins=256):
    """Number of events in each point's 2D histogram bin, used to colour the scatter by density."""
    counts, x_e, y_e = np.histogram2d(x, y, bins=bins)
    xi = np.clip(np.searchsorted(x_e, x, side='right') - 1, 0, bins - 1)
    yi = np.clip(np.searchsorted(y_e, y, side='right') - 1, 0, bins - 1)
    return counts[xi, yi]


def _style_axis(axis, scale):
    if scale == 'linear':
        return
    axis.set_ticks(to_scale(TICKS_LINEAR, scale))
    axis.set_ticklabels(TICKS_LABELS)


def density_plot(x, y, ch_x, ch_y, x_scale, y_scale, limits=None, polygon=None):
    fig = plt.figure(figsize=(8, 8), dpi=100)
    left, bottom, right, top = PLOT_AXES
    ax = fig.add_axes((left, bottom, right - left, top - bottom))

    if len(x):
        z = point_density(x, y)
        # Plot densest points last so they stay visible
        idx = z.argsort()
        ax.scatter(x[idx], y[idx], c=z[idx], s=1, linewidths=0, cmap='viridis',
                   norm=LogNorm(vmin=1, vmax=max(z.max(), 2)), rasterized=True)

    ax.set_xlabel(ch_x, fontsize=14)
    ax.set_ylabel(ch_y, fontsize=14)
    ax.tick_params(labelsize=11)
    _style_axis(ax.xaxis, x_scale)
    _style_axis(ax.yaxis, y_scale)
    ax.grid(True, linewidth=0.5, color='#E2E8F0')
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color('#94A3B8')

    if limits:
        ax.set_xlim(limits[0], limits[1])
        ax.set_ylim(limits[2], limits[3])

    if polygon is not None:
        ax.add_patch(Polygon(polygon, closed=True, edgecolor='#D946EF', fill=False, linewidth=2))

    return fig
