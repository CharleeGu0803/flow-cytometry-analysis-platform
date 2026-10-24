"""FCS loading, gating and plotting helpers."""
import logging

import matplotlib
matplotlib.use('Agg')

import flowkit as fk
import matplotlib.path as mpl_path
import matplotlib.pyplot as plt
import numpy as np
from flowutils import transforms
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon
from scipy.interpolate import interpn

log = logging.getLogger(__name__)

SCATTER_CHANNELS = ['FSC-A', 'FSC-H', 'FSC-W', 'SSC-A', 'SSC-H', 'SSC-W']

# Logicle parameters shared by sample transforms and gate/tick conversion.
LOGICLE = dict(t=262144, w=0.5, m=4.5, a=0)

TICKS_LINEAR = [-10000, -1000, -100, 0, 100, 1000, 10000, 100000]
TICKS_LABELS = ['$-10^{4}$', '$-10^{3}$', '$-10^{2}$', '0', '$10^{2}$', '$10^{3}$', '$10^{4}$', '$10^{5}$']
GRID_LOGICLE = [-0.8, -0.6, -0.4, -0.2, 0, 0.2, 0.4, 0.6, 0.8, 1.0]


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
    return np.asarray(df[fluoro_name(panel, ch)]).squeeze().astype(float)


def load_channel_pair(sample_path, panel, ch_x, ch_y, x_scale, y_scale):
    frames = load_sample(sample_path)
    return channel_values(frames, panel, ch_x, x_scale), channel_values(frames, panel, ch_y, y_scale)


def from_logicle(values):
    arr = np.asarray(values, dtype=float).reshape(-1, 1)
    return transforms.logicle_inverse(arr, [0], **LOGICLE).ravel()


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
        if native_scale(ch) == 'logicle':
            pts[:, axis] /= LOGICLE['t']
            if scale == 'linear':
                pts[:, axis] = from_logicle(pts[:, axis])
        elif scale == 'logicle':
            pts[:, axis] = to_logicle(pts[:, axis])
    return pts


def gate_vertices(coords, x_scale='linear', y_scale='linear'):
    """Normalise polygon coordinates (list of pairs or {'x','y'} dicts, in linear units) to the plot scales."""
    pts = np.array([[float(c['x']), float(c['y'])] if isinstance(c, dict) else [float(c[0]), float(c[1])]
                    for c in coords])
    if x_scale == 'logicle':
        pts[:, 0] = to_logicle(pts[:, 0])
    if y_scale == 'logicle':
        pts[:, 1] = to_logicle(pts[:, 1])
    return pts


def count_in_polygon(x, y, vertices):
    path = mpl_path.Path(vertices)
    return int(np.sum(path.contains_points(np.column_stack((x, y)))))


def density_plot(x, y, ch_x, ch_y, x_scale, y_scale, limits=None, polygon=None):
    fig, ax = plt.subplots(figsize=(8, 8))

    data, x_e, y_e = np.histogram2d(x, y, bins=[2048, 2048], density=True)
    z = interpn((0.5 * (x_e[1:] + x_e[:-1]), 0.5 * (y_e[1:] + y_e[:-1])), data,
                np.vstack([x, y]).T, method='splinef2d', bounds_error=False)
    z[np.isnan(z)] = 0.0
    # Plot densest points last so they stay visible
    idx = z.argsort()
    ax.scatter(x[idx], y[idx], c=z[idx], s=0.2, norm=Normalize(vmin=z.min(), vmax=z.max()))

    ax.set_xlabel(ch_x, fontsize=14)
    ax.set_ylabel(ch_y, fontsize=14)

    ticks = transforms.logicle(np.array(TICKS_LINEAR, dtype=float).reshape(-1, 1), [0], **LOGICLE).ravel()
    if x_scale == 'logicle':
        for v in GRID_LOGICLE:
            ax.axvline(x=v, linewidth=0.5, c='dimgray')
        ax.set_xticks(ticks)
        ax.set_xticklabels(TICKS_LABELS)
    if y_scale == 'logicle':
        for v in GRID_LOGICLE:
            ax.axhline(y=v, linewidth=0.5, c='dimgray')
        ax.set_yticks(ticks)
        ax.set_yticklabels(TICKS_LABELS)

    if limits:
        ax.set_xlim(limits[0], limits[1])
        ax.set_ylim(limits[2], limits[3])

    if polygon is not None:
        ax.add_patch(Polygon(polygon, closed=True, edgecolor='r', fill=False, linewidth=2))

    fig.tight_layout()
    return fig
