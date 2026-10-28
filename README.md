# Milestone 1 arXiv crawler — implementation in progress

**Chưa đạt toàn bộ đặc tả nghiệm thu. Không dùng bản này để crawl 5.000 ID.**
Code hiện có pipeline thử nghiệm hai dịch vụ, retry tối đa ba lần/request,
cooldown bền vững, lưu CSV/checksum, source extraction, S2 pagination,
Parquet export và notebook thử tối đa 10 ID. Không có parsing bibliography,
matching, Jupyter Book hay GitHub Pages.

## Chạy offline

Python >=3.11. Dependency ranges chưa được khóa theo Colab vì chưa chạy Colab.

```bash
python -m pip install -r src/requirements.txt
PYTHONPATH=src python -m pytest -q
```

Các test dùng httpx MockTransport. Chưa gọi API thật, chưa chạy Colab, chưa
crawl toàn range. Có test interruption/resume, last-attempt 429, malformed
HTML/gzip, backup recovery và export thiếu metadata. Đây chưa phải toàn bộ
ma trận test trong đặc tả.

## Thử trên Colab CPU

1. Đưa code đã review lên GitHub. Agent chưa commit/push; notebook clone remote
   nên sẽ không thấy những file chỉ đang nằm ở workspace local.
2. Mở `notebooks/crawl_colab.ipynb` trong Colab, chọn CPU.
3. Mount Google Drive bằng giao diện Colab; tạo/chọn thư mục dự án trên Drive.
4. Chạy cell chọn root, nhập thư mục thực tế. Đường dẫn này chỉ dùng trong
   kernel, không ghi vào config hoặc dữ liệu. Xác nhận root thực sự trên Drive.
5. Chạy cell clone/pull repo vào `code/`, cài dependency, import module.
6. Chạy cell authentication. Config bật `allow_anonymous_s2: true`; tốc độ
   anonymous là lựa chọn bảo thủ của dự án, không phải quota bảo đảm.
7. Chạy cell smoke với `limit=10`. Kết quả lưu trong `runtime/` dưới Drive root.
8. Stop giữa phiên rồi chạy lại cell. Nếu runtime chết để lại active marker,
   chỉ dùng `takeover_stale=True` sau khi chắc chắn phiên cũ đã ngừng.
9. Khi nhận key, tạo Colab Secret `SEMANTIC_SCHOLAR_API_KEY`, bật notebook access.
   Chạy lại cell authentication rồi resume. Không đưa key vào code/YAML/output.
   Local CLI đọc cùng tên biến môi trường. Không tự chuyển anonymous khi 401/403.
10. Muốn thử lại failed stages: `store.reset('failed')`, sau đó chạy lại smoke.

Không chạy hai notebook/CLI cùng dataset. Lock local không phải distributed lock.

## CLI từ project root

```bash
PYTHONPATH=src python -m crawler.cli init
PYTHONPATH=src python -m crawler.cli run --limit 10
PYTHONPATH=src python -m crawler.cli status
PYTHONPATH=src python -m crawler.cli resume --limit 10
PYTHONPATH=src python -m crawler.cli retry-failed
PYTHONPATH=src python -m crawler.cli export --run-id export-001
```

`retry-failed` chỉ reset trạng thái, không tự gọi mạng. Export không gọi API;
chỉ dùng marker/checksum hợp lệ, không xuất reference snapshot dở. Thư mục
export không được ghi đè. Raw reference thiếu arXiv ID vẫn được giữ trong JSON.

## Các khoảng thiếu phải hoàn thiện trước nghiệm thu

- Progress hiện dùng `jobs.csv` với một row/request thay vì chính xác hai schema
  `papers.csv`/`versions.csv` trong đặc tả. Chưa có migration/schema typed models.
- Chưa có toàn bộ metrics: RAM/disk sampling, events/heartbeat, elapsed từng
  paper, counters theo stage và hai CSV metrics cho export.
- Chưa có `refresh-discovery`, refresh references và lịch sử snapshot đầy đủ.
- Chưa có queue bounded riêng theo đúng hợp đồng; arXiv chọn luân phiên từ CSV
  in-memory và S2 xử lý tuần tự độc lập.
- Redirect hiện bị từ chối thành failed, chưa hỗ trợ redirect có scheduler.
- CLI mặc định chỉ chọn 10 ID; chưa hoàn thiện chế độ full-range/resume theo spec.
- Marker chưa đủ captured_at/run_id/provenance; validation/schema/guardrails và
  xử lý concurrency giữa các lệnh CLI quản trị cần bổ sung.
- Test chưa bao phủ mọi crash boundary, source traversal/limits, auth failure,
  fingerprint changes, pagination exhaustion và cancellation race.

Giữ code repo riêng với Drive runtime; report repo là milestone tương lai.

## Nguồn API đã tham khảo

- https://info.arxiv.org/help/api/user-manual.html
- https://info.arxiv.org/help/mimetypes.html
- https://api.semanticscholar.org/api-docs/graphs
- https://api.semanticscholar.org/api-docs/snippets

Việc đọc tài liệu không thay thế live smoke-test. Không khẳng định endpoint đã
được kiểm chứng bằng request thật.
