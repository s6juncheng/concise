import pytest
from tests.setup_effect_test_data import get_model, get_example_data, get_concise_model
from concise.effects.snp_effects import effect_from_model
from concise.effects.dropout import dropout_pred
from concise.effects.ism import ism
from concise.effects.gradient import gradient_pred
from copy import copy
import numpy as np
import pandas as pd
from itertools import product

def dict_grid(in_dict):
    for k in in_dict:
        if isinstance(in_dict[k], list) or isinstance(in_dict[k], tuple):
            pass
        else:
            in_dict[k] = [in_dict[k]]
    #http://stackoverflow.com/questions/5228158/cartesian-product-of-a-dictionary-of-lists
    return [dict(zip(in_dict, x)) for x in product(*in_dict.values())]


def test_gradient():
    m = get_concise_model()
    #m = get_model() # EBI cluster version - DeepSEA-like model
    ds = get_example_data()
    params = {"model": m["model"], "ref": ds["ref"], "ref_rc": ds["ref_rc"],
              "alt": ds["alt"], "alt_rc": ds["alt_rc"], "mutation_positions": ds["mutation_position"],
              "out_annotation_all_outputs": m["out_annotation"],
              "out_annotation": [None, np.array([m["out_annotation"][-1]])]}

    param_sets = dict_grid(params)

    for p in param_sets:
        preds = gradient_pred(**p)
        assert (isinstance(preds, dict))
        assert (np.all(np.in1d(["diff", "ref", "alt"], list(preds.keys()))))
        for k in preds:
            assert (isinstance(preds[k], pd.DataFrame))
            if p["out_annotation"] is None:
                assert (np.all(preds[k].columns.values == m["out_annotation"]))
            else:
                assert (np.all(preds[k].columns.values == p["out_annotation"]))



def test_dropout():
    m = get_concise_model()
    ds = get_example_data()
    params = {"model": m["model"], "ref": ds["ref"], "ref_rc": ds["ref_rc"],
              "alt": ds["alt"], "alt_rc": ds["alt_rc"], "mutation_positions": ds["mutation_position"],
              "dropout_iterations": 30, "out_annotation_all_outputs": m["out_annotation"]}

    # Shallow copies of the parameter sets
    param_sets =[params, copy(params), copy(params)]
    param_sets[1]["output_filter_mask"] = np.array([0])
    param_sets[2]["out_annotation"] = np.array([m["out_annotation"][m["out_annotation"].shape[0]-1]])

    itr = 0
    for p in param_sets:
        preds = dropout_pred(**p)
        assert(isinstance(preds, dict))
        prefix = "do"
        assert(np.all(np.in1d(["%s_pv" % prefix, "%s_cvar" % prefix, "%s_diff" % prefix], list(preds.keys()))))
        for k in preds:
            assert(isinstance(preds[k], pd.DataFrame))
            if itr ==0:
                assert(np.all(preds[k].columns.values == m["out_annotation"]))
            elif itr ==1:
                assert (np.all(preds[k].columns.values == m["out_annotation"][0]))
            elif itr ==2:
                assert (np.all(preds[k].columns.values == param_sets[2]["out_annotation"]))
        itr += 1



def test_ism():
    m = get_concise_model()
    ds = get_example_data()
    #
    param_set = {"model": [m["model"]], "ref": [ds["ref"]], "ref_rc": [ds["ref_rc"]],
            "alt": [ds["alt"]], "alt_rc": [ds["alt_rc"]], "mutation_positions": [ds["mutation_position"]],
            "out_annotation_all_outputs": [m["out_annotation"]], "diff_type" : ["log_odds", "diff"],
            "rc_handling" : ["average", "maximum"], "out_annotation" : [None, np.array([m["out_annotation"][-1]])]}
    #
    param_sets = dict_grid(param_set)
    #
    for p in param_sets:
        preds = ism(**p)
        assert(isinstance(preds, dict))
        assert(np.all(np.in1d(["ism"], list(preds.keys()))))
        for k in preds:
            assert(isinstance(preds[k], pd.DataFrame))
            if p["out_annotation"] is None:
                assert(np.all(preds[k].columns.values == m["out_annotation"]))
            else:
                assert (np.all(preds[k].columns.values == p["out_annotation"]))



def test_effect_from_model():
    m = get_concise_model()
    ds = get_example_data()
    #
    param_set = {"methods": [[gradient_pred, dropout_pred, ism]],
                 "model": [m["model"]],
                 "ref": [ds["ref"]],
                 "ref_rc": [ds["ref_rc"]],
                 "alt": [ds["alt"]],
                 "alt_rc": [ds["alt_rc"]],
                 "mutation_positions": [ds["mutation_position"]],
                 "extra_args": [[None, {"dropout_iterations": 60}, {"rc_handling" : "maximum"}]],
                 "out_annotation_all_outputs": [m["out_annotation"]],
                 "out_annotation": [np.array([m["out_annotation"][-1]])]
                 }
    #
    param_sets = dict_grid(param_set)
    #
    for p in param_sets:
        preds = effect_from_model(**p)
        assert (isinstance(preds, dict))
        assert (np.all(np.in1d(["ism", "gradient_pred", "dropout_pred"], list(preds.keys()))))
        for k in preds:
            assert (isinstance(preds[k], dict))
