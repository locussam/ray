from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from ray.rllib.evaluation.policy_graph import PolicyGraph
from ray.rllib.evaluation.torch_policy_graph import TorchPolicyGraph
from ray.rllib.models.catalog import ModelCatalog
from ray.rllib.utils.annotations import override, DeveloperAPI


@DeveloperAPI
def build_torch_policy(name,
                       loss_fn,
                       get_default_config=None,
                       stats_fn=None,
                       postprocess_fn=None,
                       extra_action_out_fn=None,
                       extra_grad_process_fn=None,
                       optimizer_fn=None,
                       before_init=None,
                       after_init=None,
                       make_model_and_action_dist=None,
                       mixins=None):
    """Helper function for creating a torch policy at runtime.

    Arguments:
        name (str): name of the graph (e.g., "PPOPolicy")
        loss_fn (func): function that returns a loss tensor the policy,
            and dict of experience tensor placeholders
        get_default_config (func): optional function that returns the default
            config to merge with any overrides
        stats_fn (func): optional function that returns a dict of
            values given the policy and batch input tensors
        postprocess_fn (func): optional experience postprocessing function
            that takes the same args as PolicyGraph.postprocess_trajectory()
        extra_action_out_fn (func): optional function that returns
            a dict of extra values to include in experiences
        extra_grad_process_fn (func): optional function that is called after
            gradients are computed and returns processing info
        optimizer_fn (func): optional function that returns a torch optimizer
            given the policy and config
        before_init (func): optional function to run at the beginning of
            policy init that takes the same arguments as the policy constructor
        after_init (func): optional function to run at the end of policy init
            that takes the same arguments as the policy constructor
        make_model_and_action_dist (func): optional func that takes the same
            arguments as policy init and returns a tuple of model instance and
            torch action distribution class. If not specified, the default
            model and action dist from the catalog will be used
        mixins (list): list of any class mixins for the returned policy class.
            These mixins will be applied in order and will have higher
            precedence than the TorchPolicyGraph class

    Returns:
        a TorchPolicyGraph instance that uses the specified args
    """

    if not name.endswith("TorchPolicy"):
        raise ValueError("Name should match *TorchPolicy", name)

    base = TorchPolicyGraph
    while mixins:

        class new_base(mixins.pop(), base):
            pass

        base = new_base

    class graph_cls(base):
        def __init__(self, obs_space, action_space, config):
            if get_default_config:
                config = dict(get_default_config(), **config)
            self.config = config

            if before_init:
                before_init(self, obs_space, action_space, config)

            if make_model_and_action_dist:
                self.model, self.dist_class = make_model_and_action_dist(
                    self, obs_space, action_space, config)
            else:
                self.dist_class, logit_dim = ModelCatalog.get_action_dist(
                    action_space, self.config["model"], torch=True)
                self.model = ModelCatalog.get_torch_model(
                    obs_space, logit_dim, self.config["model"])

            TorchPolicyGraph.__init__(self, obs_space, action_space,
                                      self.model, loss_fn, self.dist_class)

            if after_init:
                after_init(self, obs_space, action_space, config)

        @override(PolicyGraph)
        def postprocess_trajectory(self,
                                   sample_batch,
                                   other_agent_batches=None,
                                   episode=None):
            if not postprocess_fn:
                return sample_batch
            return postprocess_fn(self, sample_batch, other_agent_batches,
                                  episode)

        @override(TorchPolicyGraph)
        def extra_grad_process(self):
            if extra_grad_process_fn:
                return extra_grad_process_fn(self)
            else:
                return TorchPolicyGraph.extra_grad_process(self)

        @override(TorchPolicyGraph)
        def extra_action_out(self, model_out):
            if extra_action_out_fn:
                return extra_action_out_fn(self, model_out)
            else:
                return TorchPolicyGraph.extra_action_out(self, model_out)

        @override(TorchPolicyGraph)
        def optimizer(self):
            if optimizer_fn:
                return optimizer_fn(self, self.config)
            else:
                return TorchPolicyGraph.optimizer(self)

        @override(TorchPolicyGraph)
        def extra_grad_info(self, batch_tensors):
            if stats_fn:
                return stats_fn(self, batch_tensors)
            else:
                return TorchPolicyGraph.extra_grad_info(self, batch_tensors)

    graph_cls.__name__ = name
    graph_cls.__qualname__ = name
    return graph_cls
