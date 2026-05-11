import json
from typing import Optional

from core.registry_models import RegistryCleanupAction, RegistryCleanupPlan
from core.storage.database import get_conn


def save_plan(plan: RegistryCleanupPlan) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO registry_cleanup_plans
            (plan_id, created_at, risk_summary, status, plan_dir)
        VALUES (?,?,?,?,?)
        """,
        (
            plan.plan_id,
            plan.created_at,
            json.dumps(plan.risk_summary),
            plan.status,
            plan.plan_dir,
        ),
    )
    cur.executemany(
        """
        INSERT INTO registry_cleanup_actions
            (id, plan_id, hive, key_path, value_name, category, risk,
             is_system_critical, reg_file)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                a.id, a.plan_id, a.hive, a.key_path, a.value_name,
                a.category, a.risk, int(a.is_system_critical), a.reg_file,
            )
            for a in plan.actions
        ],
    )
    conn.commit()
    conn.close()


def load_plan(plan_id: str) -> Optional[RegistryCleanupPlan]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT plan_id, created_at, risk_summary, status, plan_dir, executed_at, restored_at "
        "FROM registry_cleanup_plans WHERE plan_id = ?",
        (plan_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    cur.execute(
        "SELECT id, plan_id, hive, key_path, value_name, category, risk, is_system_critical, reg_file "
        "FROM registry_cleanup_actions WHERE plan_id = ?",
        (plan_id,),
    )
    action_rows = cur.fetchall()
    conn.close()

    return RegistryCleanupPlan(
        plan_id=row[0],
        created_at=row[1],
        risk_summary=json.loads(row[2]),
        status=row[3],
        plan_dir=row[4],
        executed_at=row[5],
        restored_at=row[6],
        actions=[
            RegistryCleanupAction(
                id=r[0], plan_id=r[1], hive=r[2], key_path=r[3],
                value_name=r[4], category=r[5], risk=r[6],
                is_system_critical=bool(r[7]), reg_file=r[8],
            )
            for r in action_rows
        ],
    )


def list_plans() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.plan_id, p.created_at, p.risk_summary, p.status, p.plan_dir,
               p.executed_at, p.restored_at, COUNT(a.id) AS action_count
        FROM registry_cleanup_plans p
        LEFT JOIN registry_cleanup_actions a ON a.plan_id = p.plan_id
        GROUP BY p.plan_id, p.created_at, p.risk_summary, p.status, p.plan_dir,
                 p.executed_at, p.restored_at
        ORDER BY p.created_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "plan_id": r[0],
            "created_at": r[1],
            "risk_summary": json.loads(r[2]),
            "status": r[3],
            "plan_dir": r[4],
            "executed_at": r[5],
            "restored_at": r[6],
            "action_count": r[7],
        }
        for r in rows
    ]


def update_plan_status(plan_id: str, status: str, timestamp: str) -> None:
    conn = get_conn()
    if status == "executed":
        conn.execute(
            "UPDATE registry_cleanup_plans SET status=?, executed_at=? WHERE plan_id=?",
            (status, timestamp, plan_id),
        )
    elif status == "restored":
        conn.execute(
            "UPDATE registry_cleanup_plans SET status=?, restored_at=? WHERE plan_id=?",
            (status, timestamp, plan_id),
        )
    conn.commit()
    conn.close()
