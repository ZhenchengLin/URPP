from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "README.md",
    ROOT / "docs" / "00_product_spec.md",
    ROOT / "docs" / "01_architecture.md",
    ROOT / "docs" / "02_learning_objective_evidence_student_state.md",
    ROOT / "docs" / "03_state_update_engine.md",
    ROOT / "backend" / "app" / "main.py",
    ROOT / "backend" / "app" / "domain" / "learning" / "models.py",
    ROOT / "backend" / "app" / "domain" / "student" / "models.py",
    ROOT / "evaluation" / "README.md",
]

missing = [
    str(path.relative_to(ROOT))
    for path in REQUIRED
    if not path.exists()
]

if missing:
    raise SystemExit(
        f"Missing required URPP files: {missing}"
    )

print("URPP scaffold OK")
