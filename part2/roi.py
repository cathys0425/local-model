"""Capacity scenario, not measured production ROI. All costs are explicit inputs."""
import argparse
import json


def scenario(volume, baseline_minutes, coverage, review_minutes, loaded_hourly, monthly_cost, setup_cost):
    if volume < 0 or baseline_minutes < 0 or review_minutes < 0 or loaded_hourly < 0 or monthly_cost < 0 or setup_cost < 0:
        raise ValueError("Times, volumes and costs must be nonnegative")
    if not 0 <= coverage <= 1:
        raise ValueError("Coverage must be between zero and one")
    hours = volume * coverage * (baseline_minutes - review_minutes) / 60
    gross = hours * loaded_hourly
    net = gross - monthly_cost
    return {"claim_type": "hypothetical capacity value; not observed savings", "hours_freed_monthly": round(hours, 2),
            "gross_capacity_value_monthly": round(gross, 2), "net_capacity_value_monthly": round(net, 2),
            "first_year_net_capacity_value": round(net * 12 - setup_cost, 2),
            "setup_payback_months": round(setup_cost / net, 2) if net > 0 else None,
            "break_even_coverage": monthly_cost / (volume * (baseline_minutes - review_minutes) / 60 * loaded_hourly)
             if volume * (baseline_minutes - review_minutes) * loaded_hourly > 0 else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--volume", type=float, default=3000, help="Exceptions per month")
    p.add_argument("--baseline-minutes", type=float, default=8)
    p.add_argument("--coverage", type=float, default=.6, help="Fraction actually accepting the assisted workflow")
    p.add_argument("--review-minutes", type=float, default=3, help="Total human effort on covered cases, including corrections")
    p.add_argument("--loaded-hourly", type=float, default=45)
    p.add_argument("--monthly-cost", type=float, required=True, help="Compute, OCR, operations, support and recurring costs")
    p.add_argument("--setup-cost", type=float, required=True, help="Integration, validation and rollout cost")
    args = vars(p.parse_args())
    print(json.dumps({"assumptions": args, "result": scenario(**args)}, indent=2))


if __name__ == "__main__":
    main()
