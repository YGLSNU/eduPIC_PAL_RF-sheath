"""Preserve restored aggregates without inventing missing per-block measurements."""
import copy,json
from common import block_cycles
from brh_stats import assess,return_stats

def assess_available(blocks,history,criteria,gap):
    restored=[p for p in blocks if (p/'recovery_aggregate.json').exists()]
    if not restored:return assess(blocks,history,criteria,gap)
    fresh=[p for p in blocks if p not in restored]
    segment=assess(fresh,history,criteria,gap)
    # Event means and UIDs can be exactly pooled. The old native block matrices
    # cannot be recovered from their mean; no cumulative confidence is claimed.
    descriptive=return_stats(blocks,criteria)
    for key in ['candidate_return_fraction','candidate_signed_work_eV']:
        descriptive[key].update(half_width=None,first_last_change=None,passed_data=False)
    descriptive.update(fraction_passed=False,work_passed=False,passed=False,
        note='Cumulative event means/counts are descriptive. Missing pre-resume native block matrices prevent the original cumulative joint stopping assessment. See post_resume_segment_assessment for available 20RF block uncertainty.')
    result=copy.deepcopy(segment)
    result.update(passed=False,background_passed=False,BRH=descriptive,
        measurement_cycles=sum(block_cycles(p) for p in blocks),
        completed_blocks=None,reason='restored_aggregate_cumulative_uncertainty_unavailable',
        uncertainty_scope='Post-resume 20RF blocks only; cumulative native means are RF-duration weighted.',
        post_resume_segment_assessment=segment,
        recovered_RF=sum(block_cycles(p) for p in restored))
    return result
