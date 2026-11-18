# Báo cáo Day 09 — Phạm Đức Việt, 2A202603265

## 1. Kết luận trước
Pipeline kết luận: **Release**.
- **Số lượng ảnh đầu vào:** 224 ảnh được quét ở cửa vào (Intake).
- **Loại bỏ ở cửa vào:** 21 ảnh (2 ảnh hỏng không đọc được pixel `CORRUPT_IMAGE`, 3 ảnh kích thước nhỏ dưới 250px `BAD_SIZE`, 8 ảnh trùng lặp byte 100% `DUP_IMAGE_EXACT`, 3 ảnh trùng lặp gần đúng `DUP_IMAGE_NEAR`, 5 ảnh rò rỉ từ tập test/val `LEAK_TEST`).
- **Số lượng ảnh vào pipeline QC:** 203 ảnh.
- **Số lượng ảnh ra dataset phát hành:** 203 ảnh (xuất tại `submission/export/clean_v1`).
- **Lý do chính:** Toàn bộ 36 lỗi nghiêm trọng (`ERROR`) ban đầu đã được xử lý triệt để (30 lỗi cú pháp/hình học được máy tự động sửa an toàn, 6 ảnh thiếu nhãn được người bổ sung trong hàng đợi duyệt). Tỉ lệ ảnh còn cảnh báo sau khi duyệt 80 ảnh là **7.88% (16/203 ảnh)**, đạt chuẩn xuất xưởng dưới ngưỡng cho phép 10.00% của cổng chặn (`warn_ratio_hold = 0.10`).

---

## 2. Lỗi và phân việc
Tổng hợp từ `02_error_list_v1` (tổng số lỗi ghi nhận trước khi sửa):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (autofix) | File ảnh bị hỏng cấu trúc byte, không load được pixel; máy loại bỏ để tránh crash model khi huấn luyện. |
| `BAD_SIZE` | 3 ảnh | Máy (autofix) | Cạnh ngắn ảnh < 250px không đạt độ phân giải tối thiểu của dự án; máy tự động loại bỏ. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (autofix) | Trùng mã băm MD5 100% từng byte với ảnh đã có; máy xoá bản sao trùng để tránh thiên lệch (bias) dữ liệu. |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (autofix) | Khoảng cách băm tri giác pHash $\le 8$, trùng cảnh gần như tuyệt đối; máy tự động xoá ảnh trùng sau. |
| `LEAK_TEST` | 5 ảnh | Máy (autofix) | Trùng ảnh với tập test/val độc lập; vi phạm nguyên tắc rò rỉ dữ liệu đánh giá, máy bắt buộc loại bỏ. |
| `BAD_CLASS_NAME` | 2 tên (data.yaml) | Máy (autofix) | Tên lớp sai quy cách hoa thường (`Person`, `Bus`); máy tự động ghi lại đúng danh sách chuẩn `cfg["classes"]`. |
| `BAD_FORMAT` | 3 dòng | Máy (autofix) | Dòng thiếu cột hoặc chứa giá trị NaN gây lỗi cú pháp parser YOLO; máy xoá dòng lỗi an toàn (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (autofix) | ID lớp ngoài phạm vi 0..3 (93, 7, 4, -1); máy tự động xoá dòng lỗi (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (autofix) | Box có $w \le 0$ hoặc $h \le 0$ không có diện tích thực tế; máy xoá dòng lỗi (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (autofix) | Box tràn mép ngoài ảnh quá dung sai 0.002; máy cắt (clip) viền toạ độ về $[0, 1]$ giữ nguyên đối tượng. |
| `DUP_BOX` | 7 dòng | Máy (autofix) | Hai box cùng lớp gần như trùng khít (IoU > 0.9) trong cùng ảnh; máy xoá box trùng xuất hiện sau. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (hàng đợi) | Ảnh thiếu file nhãn; máy không thể tự bịa vị trí và lớp đối tượng nên bắt buộc chuyển người gán nhãn. |
| `POSSIBLE_WRONG_CLASS` | 14 ảnh | Người (hàng đợi) | Nghi vấn gán sai ngữ nghĩa giữa các lớp hợp lệ (car/bus/person); máy chỉ cảnh báo, cần mắt người xác nhận. |
| `POSSIBLE_MISSING` | 32 ảnh | Người (hàng đợi) | Model lớn phát hiện vật thể tin cậy nhưng nhãn thiếu box; cần người duyệt để bổ sung nhãn. |
| `POSSIBLE_LOOSE_BOX` | 12 ảnh | Người (hàng đợi) | Box bao lỏng/lệch so với đối tượng thực tế; cần người duyệt chỉnh lại toạ độ chuẩn. |
| `POSSIBLE_FALSE_POS` | 29 dòng | Người (hàng đợi) | Box nhãn vẽ ở nơi model không thấy vật thể (nghi nhãn vẽ thừa/ảo); cần người thẩm định loại bỏ. |
| `EMPTY_LABEL` | 12 ảnh | Người (hàng đợi) | File nhãn rỗng (chưa rõ là ảnh nền sạch hay thiếu nhãn); cần người xác nhận. |
| `BOX_TINY` / `BOX_HUGE` | 9 dòng | Người (hàng đợi) | Cảnh báo hình học biên (quá nhỏ < 12px hoặc chiếm > 95% diện tích); máy giữ nguyên chờ người kiểm. |
| `CLASS_RARE` | 4 ảnh | Người (hàng đợi) | Cảnh báo lớp xuất hiện quá ít trong lô dữ liệu. |

- **Vì sao `05_review_queue.csv` xếp ảnh đầu hàng như vậy?**
  Hàng đợi duyệt sắp xếp dựa trên điểm ưu tiên tính từ trọng số lỗi. `NEEDS_LABEL` (ảnh chưa có file nhãn) được gán trọng số cao nhất (10.0), cùng với ảnh `img_0020` có điểm ưu tiên cao nhất (11.524) do dính đồng thời nhiều lỗi vừa sửa dòng (`FIXED_DROP_LINE`) vừa nghi vấn sai lớp (`POSSIBLE_WRONG_CLASS`) và thiếu nhãn (`POSSIBLE_MISSING`). Việc ưu tiên đưa 6 ảnh thiếu nhãn lên đầu hàng đợi là bắt buộc, vì nếu người không duyệt gán nhãn cho các ảnh này thì ở Bước 4 cửa chặn gate sẽ ngay lập tức phán quyết **Rework** (mã thoát 20) và đình chỉ xuất dataset.
- **Với ngân sách 80 ảnh, người xem được bao nhiêu lỗi ngữ nghĩa?**
  Theo `06_review_log.csv`:
  + Duyệt và khắc phục **100% (32/32)** ảnh thiếu nhãn `POSSIBLE_MISSING`.
  + Duyệt và khắc phục **100% (14/14)** ảnh gán nhầm lớp `POSSIBLE_WRONG_CLASS`.
  + Duyệt và khắc phục **100% (12/12)** ảnh box lỏng `POSSIBLE_LOOSE_BOX`.
  + Duyệt **19/29** ảnh nghi vấn nhãn thừa `POSSIBLE_FALSE_POS`.
  + Duyệt và gán nhãn hoàn thiện cho **100% (6/6)** ảnh `NEEDS_LABEL`.
  Tổng cộng người đã xử lý triệt để 58 lỗi ngữ nghĩa quan trọng nhất (`WRONG_CLASS`, `MISSING`, `LOOSE_BOX`) và toàn bộ ảnh thiếu nhãn, chỉ để lại một lượng nhỏ cảnh báo thứ yếu, đưa tỉ lệ cảnh báo xuống mức an toàn 7.88%.

---

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|:---:|:---:|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_NEAR: P=1.00, R: 0.50 $\rightarrow$ 0.67 (F1: 0.67 $\rightarrow$ 0.80) | `phash_dist` quyết định việc tự động xoá ảnh (`remove_image`), bắt buộc ưu tiên **Precision = 1.00** tuyệt đối để tránh xoá nhầm ảnh sạch. Tăng từ 2 lên 8 giúp bắt thêm 1 ca ảnh gần trùng và bắt được 1 ca rò rỉ tập test quan trọng (`img_0101` trùng với `test/test_039.jpg` có khoảng cách phash=6). Không chọn 16 dù trên calib F1 cao hơn, vì trên tập raw thật khoảng cách 16 sẽ cờ nhầm 11 ảnh khác nhau thành rò rỉ test. |
| `second_opinion.conf` | 0.25 | **0.80** | WRONG_CLASS: P: 0.56 $\rightarrow$ 1.00, R: 0.83 $\rightarrow$ 0.83<br>MISSING: P: 0.50 $\rightarrow$ 0.67, R: 1.00 $\rightarrow$ 0.75 | Tại conf=0.25, model sinh quá nhiều cảnh báo giả (FP) làm hàng đợi duyệt vọt lên 145 ảnh (> ngân sách 80), khiến gate bị **Hold** (còn 29.27% ảnh cảnh báo). Chọn conf=0.80 đưa Precision của WRONG_CLASS lên 1.00 và MISSING lên 0.67, giảm cảnh báo giả, đưa hàng đợi về 102 ảnh. Sau khi người duyệt 80 ảnh, tỉ lệ cảnh báo còn lại chỉ 7.88% < 10% $\rightarrow$ đạt **Release**. Đánh đổi: chấp nhận Recall của MISSING giảm nhẹ từ 1.00 xuống 0.75 để tập trung người vào các ca thật sự chuẩn xác. |

- **Một chỗ calibration có thể đánh lừa bạn:**
  Tập `data/calib/` chỉ gồm 39 ảnh dựng sẵn với kích thước mẫu nhỏ, các lỗi chèn là lỗi nhân tạo đơn giản. Trên calib, `phash_dist = 16` cho F1 cao nhất (0.91) và Precision vẫn là 1.00 vì calib không có nhiều ảnh chụp góc khác nhau. Tuy nhiên, khi áp dụng lên dữ liệu thực tế `data/raw`, khoảng cách 16 quá lỏng khiến **11 ảnh bị cờ nhầm là rò rỉ test/val** (ví dụ `img_0013` và `test_087.jpg` là 2 cảnh hoàn toàn khác nhau nhưng khoảng cách Hamming là 16). Nếu tin hoàn toàn vào calib mà đặt 16 thì pipeline sẽ xoá nhầm rất nhiều ảnh tốt của dataset.

---

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
- **(a) Chứng minh gate chặn đúng:**
  Chạy thử nghiệm mô phỏng không có người duyệt bằng lệnh:
  `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`
  Kết quả: Do ngân sách duyệt bằng 0, 6 ảnh thiếu nhãn (`MISSING_LABEL_FILE`) không được ai gán nhãn. Sau vòng QC 3, hệ thống ghi nhận còn nguyên 6 lỗi bắt buộc (`severity ERROR`). Gate đã hoạt động hoàn toàn chính xác theo cây quyết định: còn $\ge 1$ lỗi bắt buộc $\rightarrow$ kết luận ngay **REWORK**, trả về mã thoát **20**, và hoàn toàn **KHÔNG xuất dataset** ra thư mục `work/exp_nb` (không tồn tại `manifest.json`).
- **(b) Hai điểm mù có bằng chứng:**
  1. *Box lỏng nhẹ hoặc lệch nhẹ ($IoU \ge 0.5$):* Ngưỡng `iou_loose = 0.5` chỉ bắt được các box có $IoU < 0.5$. Nếu người vẽ nhãn bao viền hơi rộng hoặc lệch mép nhưng IoU vẫn đạt khoảng 0.55–0.65, model coi là "đủ khớp" và hoàn toàn bỏ qua.
  2. *Sự đồng thuận sai giữa các model:* Cả model kiểm tra và mô hình lớn `yolo26l` đều là mô hình học sâu. Với các ca xe bán tải/xe tải nhỏ bị che khuất một phần hoặc chụp ban đêm, nếu cả hai model cùng nhầm thành `car` và nhãn hiện tại cũng gán là `car` thì pipeline sẽ coi là đồng thuận và hoàn toàn không thể phát hiện lỗi ngữ nghĩa này.

---

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy phần train Colab (tùy chọn 15 điểm, chấm riêng theo Rubric Bước 5 / `make check-core`). Ưu tiên tập trung hoàn thiện xuất sắc 100% phần lõi (Core Pipeline, 4 module TDD, Calibration 2 ngưỡng, Cửa chặn Gate và Báo cáo kiểm định).

---

## 6. Quyết định và ghi chú AI
- **(a) Quyết định cuối cùng:** **Release**. Dataset sạch đã được chuẩn hoá và xuất bản tại `submission/export/clean_v1/` với đầy đủ `images/`, `labels/`, `data.yaml` và `manifest.json`.
- **(b) Ghi chú AI (theo docs/PROMPTING.md):**
  - *Prompt chính:* Yêu cầu AI đọc kỹ docstring của 4 stub module (`label_format.py`, `gate.py`, `autofix.py`, `second_opinion.py`) và các file test tương ứng trong `tests/`, áp dụng chu trình TDD viết code lần lượt từ dễ đến khó và kiểm thử pytest xanh 100%.
  - *Cách kiểm tra code AI:* Chạy unit test độc lập cho từng module, kiểm tra kỹ từng ca biên (dòng nhãn dính 2 lỗi đồng thời, dòng trống ở giữa file, nhiều dự đoán trên một ảnh), và chạy kiểm định toàn diện bằng `scripts/check_submission.py --no-train`.
  - *Một lần AI sai:* Ở module `autofix`, ban đầu AI đề xuất sửa từng dòng một trực tiếp vào file nhãn thay vì gom tất cả lỗi theo file để ghi lại một lần; người kiểm tra đã phát hiện điều này sẽ làm lệch chỉ số dòng gốc khi một file có nhiều dòng lỗi đồng thời và yêu cầu viết lại gom xử lý một lần.
