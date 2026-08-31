import pytest
from latent_space_aggregation_attacks.evaluation.statistics import wilson_interval,mcnemar_exact,holm_adjust,paired_wilcoxon
def test_registered_statistics():
    low,high=wilson_interval(50,100); assert low<.5<high; assert mcnemar_exact([True,True,False],[True,False,True])["p_value"]==1
    assert holm_adjust([.01,.04,.2])==pytest.approx([.03,.08,.2]); assert paired_wilcoxon([1,2],[1,2])["p_value"]==1
from latent_space_aggregation_attacks.evaluation.metrics import removal_optimization_progress_pct


def test_removal_progress_is_normalized_to_the_rejection_threshold():
    assert removal_optimization_progress_pct("tree_ring", 0.0, 0.025, 0.05) == 50.0
    assert removal_optimization_progress_pct("ringid", 0.0, 0.05, 0.05) == 100.0
    assert removal_optimization_progress_pct("gaussian_shading", 1.0, 0.82421875, 0.6484375) == 50.0
