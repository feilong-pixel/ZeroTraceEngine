from core.registry_models import RegistryIssueItem, RegistryScannerReport
from core.storage.database import get_conn


def save_registry_scan_results(
    items: list[RegistryIssueItem],
    reports: list[RegistryScannerReport] | None = None,
) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM registry_scan_results")
    cur.execute("DELETE FROM registry_scan_reports")
    cur.executemany(
        """
        INSERT INTO registry_scan_results
            (id, category, risk, source, hive, key_path, value_name,
             value_data, target_path, description, rule_id,
             confidence, validation_status, skip_reason,
             is_system_critical, selected, ignored)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                item.id, item.category, item.risk, item.source,
                item.hive, item.key_path, item.value_name,
                item.value_data, item.target_path, item.description,
                item.rule_id, item.confidence, item.validation_status,
                item.skip_reason, int(item.is_system_critical),
                int(item.selected), int(item.ignored),
            )
            for item in items
        ],
    )
    cur.executemany(
        """
        INSERT INTO registry_scan_reports
            (hive, key_path, scan_type, status, checked, issues, skipped, error)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        [
            (
                report.hive,
                report.key_path,
                report.scan_type,
                report.status,
                report.checked,
                report.issues,
                report.skipped,
                report.error,
            )
            for report in (reports or [])
        ],
    )
    conn.commit()
    conn.close()


def load_registry_scan_results() -> list[RegistryIssueItem]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, category, risk, source, hive, key_path, value_name,
               value_data, target_path, description, rule_id,
               confidence, validation_status, skip_reason,
               is_system_critical, selected, ignored
        FROM registry_scan_results
        ORDER BY risk DESC, category
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [
        RegistryIssueItem(
            id=r[0], category=r[1], risk=r[2], source=r[3],
            hive=r[4], key_path=r[5], value_name=r[6],
            value_data=r[7], target_path=r[8], description=r[9],
            rule_id=r[10], confidence=r[11], validation_status=r[12],
            skip_reason=r[13], is_system_critical=bool(r[14]),
            selected=bool(r[15]), ignored=bool(r[16]),
        )
        for r in rows
    ]


def clear_registry_scan_results() -> None:
    conn = get_conn()
    conn.execute("DELETE FROM registry_scan_results")
    conn.execute("DELETE FROM registry_scan_reports")
    conn.commit()
    conn.close()


def load_registry_scan_reports() -> list[RegistryScannerReport]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT hive, key_path, scan_type, status, checked, issues, skipped, error
        FROM registry_scan_reports
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [
        RegistryScannerReport(
            hive=r[0],
            key_path=r[1],
            scan_type=r[2],
            status=r[3],
            checked=r[4],
            issues=r[5],
            skipped=r[6],
            error=r[7],
        )
        for r in rows
    ]


def count_registry_scan_results() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM registry_scan_results")
    n = cur.fetchone()[0]
    conn.close()
    return n
