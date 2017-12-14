#mpiexec -n 4 python pc_simple_optimize_network.py

from mpi4py import MPI
from neuron import h
import importlib
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moopgen import *

kwargs = {'cvode': False}
subworld_size = 2
target_val = {'EPSP': 10.}
target_range = {'EPSP': 4.}


global_context = Context()
global_context.kwargs = kwargs
global_context.sleep = False
comm = MPI.COMM_WORLD
global_context.comm = comm


def setup_ranks():
    module_names = ['pc_simple_network_submodule']
    modules = []
    get_features_funcs = []
    get_objectives_funcs = []
    for module_name in module_names:
        m = importlib.import_module(module_name)
        modules.append(m)
        get_features_funcs.append(getattr(m, 'get_EPSP_features'))
        get_objectives_funcs.append(getattr(m, 'get_objectives'))
    global_context.modules = modules
    #global_context.get_features_funcs = get_features_funcs
    global_context.get_features_funcs = get_features_funcs * 2 #So that we can try two rounds of calculations
    #global_context.get_objectives_funcs = get_objectives_funcs
    global_context.get_objectives_funcs = get_objectives_funcs * 2


def init_engine(**kwargs):
    setup_funcs = []
    for m in set(global_context.modules):
        config_func = getattr(m, 'config_engine')
        if not callable(config_func):
            raise Exception('parallel_optimize: init_engine: submodule: %s does not contain required callable: '
                            'config_engine' % str(m))
        else:
            config_func(global_context.comm, subworld_size, target_val, target_range, **kwargs)
        setup_funcs.append(getattr(m, 'setup_network'))
    #global_context.setup_funcs = setup_funcs
    global_context.setup_funcs = setup_funcs * 2 #So we can try two rounds of calculations


def run_optimization():
    #should this happen only on one processor (rank = 0)? Parallel context exists only on the other module.

    #normally, we would be looping through multiple generations (each generated by param_gen)
    generation = [0.01, 0.2, 0.5, 1.]
    features = get_all_features(generation)
    features, objectives = get_all_objectives(features)
    print 'final features'
    print features
    print 'final objectives'
    print objectives
    getattr(global_context.modules[0], 'end_optimization')()

def get_all_features(generation):
    """
    Note: differs from old parallel_optimize script in that we are no longer mapping each indiv to a separate feature_function call
    :param generation:
    :return:
    """
    pop_ids = range(len(generation))
    curr_generation = {pop_id: generation[pop_id] for pop_id in pop_ids}
    features_dict = {pop_id: {} for pop_id in pop_ids}

    for ind in xrange(len(global_context.get_features_funcs)):
        next_generation = {}
        indivs = [{'pop_id': pop_id, 'x': curr_generation[pop_id], 'features': features_dict[pop_id]}
                  for pop_id in curr_generation]
        feature_function = global_context.get_features_funcs[ind]
        print 'start round %i' %ind
        results = feature_function(indivs)
        for i, result in enumerate(results):
            if None in result['result_list']:
                print 'Individual: %i failed %s' %(result['pop_id'], str(str(feature_function)))
                features_dict[result['pop_id']] = None
            else:
                next_generation[result['pop_id']] = generation[result['pop_id']]
                #do filter features processing here
                new_features = {key: value for result_dict in result['result_list'] for key, value in result_dict.iteritems()}
                features_dict[result['pop_id']].update(new_features)
        curr_generation = next_generation
        #print 'features after round %i' %ind
        #print features_dict
    features = features_dict.values()
    return features


def get_all_objectives(features):
    objectives_dict = {pop_id: {} for pop_id in range(len(features))}
    for objective_function in global_context.get_objectives_funcs:
        new_features, new_objectives = objective_function(features)
        for pop_id, objective in new_objectives.iteritems():
            objectives_dict[pop_id].update(objective)
            features[pop_id] = new_features[pop_id]
    objectives = objectives_dict.values()
    return features, objectives


if __name__ == '__main__':
    setup_ranks()
    init_engine()
    print global_context.modules[0].report_pc_id()
    run_optimization()
