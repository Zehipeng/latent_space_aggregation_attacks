import pytest
from latent_space_aggregation_attacks.evaluation.statistics import wilson_interval,mcnemar_exact,holm_adjust,paired_wilcoxon
def test_registered_statistics():
    low,high=wilson_interval(50,100); assert low<.5<high; assert mcnemar_exact([True,True,False],[True,False,True])["p_value"]==1
    assert holm_adjust([.01,.04,.2])==pytest.approx([.03,.08,.2]); assert paired_wilcoxon([1,2],[1,2])["p_value"]==1
