"""Service for aggregating dicamba compliance statistics (F4 Phase 6)."""
from services.user import _get_service_client


def aggregate_gate_stats() -> dict:
    """Queries all spray_records via service-role client and aggregates per-gate status counts."""
    result = (
        _get_service_client()
        .table("spray_records")
        .select("gates")
        .execute()
    )

    data = result.data or []
    total_records = len(data)
    gates_summary = {
        "A": {"pass": 0, "fail": 0, "needs_confirmation": 0},
        "B": {"pass": 0, "fail": 0, "needs_confirmation": 0},
        "C": {"pass": 0, "fail": 0, "needs_confirmation": 0},
        "D": {"pass": 0, "fail": 0, "needs_confirmation": 0},
    }

    for record in data:
        gates = record.get("gates") or []
        for g in gates:
            gate_id = g.get("gate")
            status = g.get("status")
            if gate_id in gates_summary and status in gates_summary[gate_id]:
                gates_summary[gate_id][status] += 1

    return {
        "total_records": total_records,
        "gates": gates_summary,
    }
