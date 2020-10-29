import sys
import warnings

import numpy as np
import xarray as xr
from tqdm import tqdm

from carbonplan_forests import fit, load

warnings.simplefilter('ignore', category=RuntimeWarning)

args = sys.argv

if len(args) < 2:
    store = 'local'
else:
    store = args[1]

coarsen_fit = 16
coarsen_predict = 4
tlim = (1984, 2018)
data_vars = ['ppt', 'tavg']
fit_vars = ['ppt', 'tavg']

print('[fire] loading data')
mask = load.nlcd(store=store, classes='all', year=2001)
groups = load.nftd(store=store, groups='all', coarsen=coarsen_fit, mask=mask, area_threshold=1500)
climate = load.terraclim(
    store=store, tlim=tlim, coarsen=coarsen_fit, data_vars=data_vars, mask=mask
)
mtbs = load.mtbs(store=store, coarsen=coarsen_fit, tlim=tlim)
mtbs['vlf'] = mtbs['vlf'] > 0

print('[fire] fitting model')
model = fit.fire(x=climate[fit_vars], y=mtbs['vlf'], f=groups)

print('[fire] setting up evaluation')
final_mask = load.nlcd(store=store, year=2016, coarsen=coarsen_predict, classes=[41, 42, 43, 90])
final_mask.values = final_mask.values > 0.5
ds = xr.Dataset()

print('[fire] evaluating on training data')
groups = load.nftd(
    store=store, groups='all', mask=mask, coarsen=coarsen_predict, area_threshold=1500
)
climate = load.terraclim(
    store=store, tlim=(2005, 2014), coarsen=coarsen_predict, data_vars=data_vars, mask=mask
)
prediction = model.predict(x=climate[fit_vars], f=groups)
ds['historical'] = prediction['prob'].mean('time') * final_mask.values

print('[fire] evaluating on future climate')
targets = list(map(lambda x: str(x), np.arange(2020, 2120, 20)))
cmip_model = 'BCC-CSM2-MR'
scenarios = ['ssp245', 'ssp370', 'ssp585']
for scenario in tqdm(scenarios):
    results = []
    for target in targets:
        tlim = (int(target) - 5, int(target) + 4)
        climate = load.cmip(
            store=store,
            model=cmip_model,
            coarsen=coarsen_predict,
            scenario=scenario,
            tlim=tlim,
            data_vars=data_vars,
        )
        prediction = model.predict(x=climate[fit_vars], f=groups)
        results.append(prediction['prob'].mean('time') * final_mask.values)
    da = xr.concat(results, dim=xr.Variable('year', targets))
    ds[cmip_model + '_' + scenario] = da

ds.to_zarr('data/fire.zarr')
