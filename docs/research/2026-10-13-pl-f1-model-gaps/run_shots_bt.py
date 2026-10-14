import sys, runpy; sys.path.insert(0,'.')
import common  # blocks network
sys.path.insert(0,'../PL_Predictor/src'); sys.argv=['x','--cache-dir','../PL_Predictor/data/cache','--out','shots_bt.csv']
runpy.run_module('pl_predictor.evaluate.player_shots_backtest', run_name='__main__')
