"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems_set = set(image_stems)
    n_images = len(image_stems)
    reviewed_set = set(reviewed) if reviewed else set()
    warn_ratio_hold = cfg.get("gate", {}).get("warn_ratio_hold", 0.10)

    # Đếm lỗi bắt buộc (severity ERROR)
    # Lỗi bắt buộc không bao giờ bị bỏ qua kể cả ở ảnh reviewed
    errors = [i for i in issues if i.severity == ERROR and (i.image in stems_set or i.image in ("<dataset>", "data.yaml"))]
    n_errors = len(errors)

    # Đếm ảnh có cảnh báo (WARN)
    # Chỉ tính ảnh nằm trong image_stems và chưa nằm trong reviewed
    warn_images = {i.image for i in issues if i.severity == WARN and i.image in stems_set and i.image not in reviewed_set}
    n_warn_images = len(warn_images)

    warn_ratio = round(n_warn_images / n_images, 4) if n_images > 0 else 0.0

    reasons = []
    if n_errors > 0:
        decision = "Rework"
        reasons.append(f"Còn {n_errors} lỗi bắt buộc (severity ERROR) cần sửa")
        if n_warn_images > 0:
            reasons.append(f"Có {n_warn_images}/{n_images} ảnh có cảnh báo (tỉ lệ {warn_ratio * 100:.2f}%)")
    elif warn_ratio >= warn_ratio_hold:
        decision = "Hold"
        reasons.append(f"Tỉ lệ ảnh có cảnh báo {warn_ratio * 100:.2f}% ({n_warn_images}/{n_images} ảnh) >= ngưỡng {warn_ratio_hold * 100:.2f}%")
    else:
        decision = "Release"
        reasons.append(f"Đạt chuẩn xuất: 0 lỗi bắt buộc, tỉ lệ cảnh báo {warn_ratio * 100:.2f}% ({n_warn_images}/{n_images} ảnh) < ngưỡng {warn_ratio_hold * 100:.2f}%")

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
