import keras
import numpy as np
import pandas as pd
from scipy.stats.stats import ttest_rel



## TODO: Move to layer definition:
from keras.layers.core import Dropout
import keras.backend as K
class BiDropout(Dropout):
    """Applies Dropout to the input, no matter if in learning phase or not.
    """
    def __init__(self, bi_dropout = True, **kwargs):
        #__init__(self, rate, noise_shape=None, seed=None, **kwargs)
        super(BiDropout, self).__init__(**kwargs)
        self.bi_dropout = bi_dropout
    #
    def call(self, inputs, training=None):
        if 0. < self.rate < 1.:
            noise_shape = self._get_noise_shape(inputs)
            #
            def dropped_inputs():
                return K.dropout(inputs, self.rate, noise_shape, seed=self.seed)
            if self.bi_dropout:
                # K.in_train_phase returns the first argument if in training phase otherwise the second
                #return K.in_train_phase(dropped_inputs, inputs, training=training)
                # Taken from keras.backend.tensorflow_backend
                if callable(dropped_inputs):
                    return dropped_inputs()
                else:
                    return dropped_inputs
            else:
                return K.in_train_phase(dropped_inputs, inputs,
                                        training=training)
        return inputs
    #
    @classmethod
    def create_from_dropout(cls, dropout_obj):
        if not isinstance(dropout_obj, Dropout):
            raise Exception("Only Dropout objects can be converted this way!")
        kwargs = dropout_obj.get_config()
        # alternatively can we use "get_config" in combination with (Layer.__init__)allowed_kwargs?
        return cls(**kwargs)

def replace_dict_values(in_dict, from_value, to_value):
    out_dict = {}
    for k in in_dict:
        if isinstance(in_dict[k], dict):
            out_dict[k] = replace_dict_values(in_dict[k], from_value, to_value)
        elif isinstance(in_dict[k], list):
            out_dict[k] = []
            for el in in_dict[k]:
                if isinstance(el, dict):
                    out_dict[k].append(replace_dict_values(el, from_value, to_value))
                else:
                    if el == from_value:
                        out_dict[k].append(to_value)
                    else:
                        out_dict[k].append(el)
        else:
            if in_dict[k] == from_value:
                out_dict[k] = to_value
            else:
                out_dict[k] = in_dict[k]
    return out_dict


def pred_do(model, input_data, output_filter_mask, dropout_iterations):
    diff_outputs = []
    for k in range(dropout_iterations):
        # diff_outputs.append(np.array(self.predict_vals(input_data)[0]))
        diff_outputs.append(np.array(model.predict(input_data)[..., output_filter_mask]))
    return np.array(diff_outputs)


def subset_array_by_index(arr, idx):
    assert (np.all(np.array(arr.shape[1:]) == np.array(idx.shape[1:])))
    assert (arr.shape[0]/2 == idx.shape[0])
    pred_out_sel = []
    for c in range(arr.shape[1]):
        sel_idxs = np.arange(arr.shape[0] / 2) * 2 + idx[:, c]
        pred_out_sel.append(arr[sel_idxs, c])
    return np.array(pred_out_sel).T

def overwite_by(main_arr, alt_arr, idx):
    assert (np.all(np.array(main_arr.shape[1:]) == np.array(idx.shape[1:])))
    assert (main_arr.shape[0] == idx.shape[0])
    assert (alt_arr.shape[0] == idx.shape[0])
    for c in range(main_arr.shape[1]):
        main_arr[idx[:, c], c] = alt_arr[idx[:, c],c]
    return main_arr

def test_overwite_by():
    a = np.array([[1, 2], [4, 5]])
    b = np.array([[1, 8], [4, 5]])
    overwite_by(a,b,a < b)
    assert(a[0,1]==8)

# The function called from outside
def dropout_pred(model, ref, ref_rc, alt, alt_rc, mutation_positions, out_annotation_all_outputs,
                 output_filter_mask = None,out_annotation= None, dropout_iterations = 30):
    prefix = "do"

    seqs = {"ref": ref, "ref_rc": ref_rc, "alt": alt, "alt_rc": alt_rc}

    assert np.all([np.array(ref.shape) == np.array(seqs[k].shape) for k in seqs.keys() if k != "ref"])
    assert ref.shape[0] == mutation_positions.shape[0]
    assert len(mutation_positions.shape) == 1

    # determine which outputs should be selected
    if output_filter_mask is None:
        if out_annotation is None:
            output_filter_mask = np.arange(out_annotation_all_outputs.shape[0])
        else:
            output_filter_mask = np.where(np.in1d(out_annotation_all_outputs, out_annotation))[0]

    # make sure the labels are assigned correctly
    out_annotation = out_annotation_all_outputs[output_filter_mask]

    # Instead of loading the model from a json file I will transfer the model architecture + weights in memory
    model_config = model._updated_config()
    alt_config = replace_dict_values(model_config, u"Dropout", u"BiDropout")


    # Custom objects have to be added before correctly!
    alt_model = keras.layers.deserialize(alt_config)

    # Transfer weights and biases
    alt_model.set_weights(model.get_weights())

    # ANALOGOUS TO ISM:
    # predict
    preds = {}
    for k in seqs:
        preds[k] = pred_do(alt_model, seqs[k], output_filter_mask=output_filter_mask, dropout_iterations = dropout_iterations)

    t, prob = ttest_rel(preds["ref"], preds["alt"], axis=0)
    t_rc, prob_rc = ttest_rel(preds["ref_rc"], preds["alt_rc"], axis=0)

    # fwd and rc are independent here... so this can be done differently here...

    sel = (np.abs(prob) > np.abs(prob_rc)).astype(np.int)  # Select the LOWER p-value among fwd and rc

    out_dict = {}

    out_dict["%s_pv" % prefix] = pd.DataFrame(overwite_by(prob, prob_rc, sel), columns=out_annotation)

    pred_means = {}
    pred_vars = {}
    pred_cvar2 = {}
    for k in preds:
        pred_means[k] = np.mean(preds[k], axis=0)
        pred_vars[k] = np.var(preds[k], axis=0)
        pred_cvar2[k] = pred_vars[k] / (pred_means[k] ** 2)

    mean_cvar = np.sqrt((pred_cvar2["ref"] + pred_cvar2["alt"]) / 2)
    mean_cvar_rc = np.sqrt((pred_cvar2["ref_rc"] + pred_cvar2["alt_rc"]) / 2)

    mean_cvar = overwite_by(mean_cvar, mean_cvar_rc, sel)
    ref_mean = overwite_by(pred_means["ref"], pred_means["ref_rc"], sel)
    alt_mean = overwite_by(pred_means["alt"], pred_means["alt_rc"], sel)
    ref_var = overwite_by(pred_vars["ref"], pred_vars["ref_rc"], sel)
    alt_var = overwite_by(pred_vars["alt"], pred_vars["alt_rc"], sel)

    out_dict["%s_ref_mean" % prefix] = pd.DataFrame(ref_mean,columns=out_annotation)
    out_dict["%s_alt_mean" % prefix] = pd.DataFrame(alt_mean,columns=out_annotation)

    out_dict["%s_ref_var" % prefix] = pd.DataFrame(ref_var,columns=out_annotation)
    out_dict["%s_alt_var" % prefix] = pd.DataFrame(alt_var,columns=out_annotation)

    out_dict["%s_cvar" % prefix] = pd.DataFrame(mean_cvar,columns=out_annotation)

    out_dict["%s_diff" % prefix] = out_dict["%s_alt_mean" % prefix] - out_dict["%s_ref_mean" % prefix]

    return out_dict




