# Milestone 1 arXiv crawler

Python >=3.11, Colab CPU; inclusive range `2504.02523`–`2504.07522`.
Metadata và source arXiv dùng chung scheduler nối tiếp; S2 có limiter riêng.
Mỗi request tối đa ba attempts, gồm cả 429; source validation dùng cùng budget.
Cooldown và attempts được lưu trước khi tiếp tục. Không tự retry failed khi resume.

## Kết quả smoke do người dùng cung cấp

Bản đầu đã chạy 10 ID trên Colab: discovery 10, version metadata 14,
reference snapshots 10, source thành công 7 và thất bại 7.
Hai source thất bại do HTTP 429. Năm archive còn lại được người dùng kiểm tra:
`gzip.open()` đọc đến cuối đều báo EOFError (thiếu end-of-stream marker).
Đã xác nhận archive bị cắt; chưa xác định tầng gây cắt (server/network/Colab).
API key Semantic Scholar không thay đổi rate limit arXiv.

Bản cập nhật phân biệt `payload_gzip_truncated`, `payload_invalid_gzip`,
`payload_invalid_tar`, `transport_ReadTimeout` và các mã lỗi khác; lưu response
metadata cùng số bytes, checksum, content type/encoding/length. Không đánh dấu
archive hỏng là complete/no_tex. Chưa chạy live smoke cho bản cập nhật.

## Cài và kiểm thử offline

```bash
python -m pip install -r src/requirements.txt
PYTHONPATH=src python -m pytest -q
```

Dependency ranges chưa khóa theo Colab vì chưa thu thập package snapshot từ
smoke bản cập nhật. Mỗi run tự lưu phiên bản package trong environment.json.

## Dữ liệu và tương thích với bản đầu

- `runtime/progress/jobs.csv`: ledger bền vững cho attempts từng request/page,
  giữ tương thích dữ liệu smoke cũ. Không xóa hoặc sửa tay file này.
- `papers.csv`, `versions.csv`: snapshots theo schema đặc tả, tạo tự động từ
  ledger khi checkpoint. `status_counts()` đếm references theo bài, không cộng
  page rows. Đây là lựa chọn tương thích: ledger giữ lịch sử retry chi tiết,
  hai snapshots là view tái tạo được, không phải ba nguồn trạng thái độc lập.
- `services.json`: cooldown và rolling-window S2 tồn tại qua restart.
- Kết quả chỉ hợp lệ khi marker/checksum khớp. Legacy marker vẫn được đọc;
  marker mới thêm UTC captured_at, run_id và số byte.
- `reference-staging/`: raw pages có checksum/fingerprint để resume giữa trang.
- `history/`: kết quả cũ được giữ khi chủ động refresh.
- `metrics/<run_id>/`: environment, samples RAM/disk, paper elapsed và summary.
- `logs/<run_id>/events.jsonl`: request, retry, wait heartbeat, commit, recovery.
- `exports/<export_id>/`: Parquet, paper/version metrics CSV, run metrics,
  reference conflict audit và manifest checksums/fingerprints.

Mọi project path là tương đối với root đang làm việc. CSV UTF-8 dùng quoting;
ô trống biểu thị thiếu dữ liệu. Dates thiếu giữ null, không suy ngày từ year.
RAM trung bình có trọng số thời gian; peak RAM/disk là peak quan sát được,
sampling có thể bỏ lỡ spike. Các metrics cũ chưa đo không được dựng lại giả.

## Cập nhật Colab đang có dữ liệu

1. Push bản code cập nhật lên GitHub, rồi mở `notebooks/crawl_colab.ipynb`.
2. Chọn CPU, mount Drive bằng giao diện Files → Mount Drive.
3. Chọn đúng project root đã dùng ở smoke cũ. Không tạo runtime mới.
4. Chạy cell clone/pull và cài dependency. Nếu đã import crawler trước khi pull,
   restart runtime, mount Drive lại rồi chạy lại các cell để dùng code mới.
5. Giữ secret `SEMANTIC_SCHOLAR_API_KEY` trong Colab Secrets, bật Notebook access.
   Cell authentication chỉ in `key` hoặc `anonymous`. Không dán key vào code.
6. Chạy status/diagnostics. `diagnose_sources(config)` chỉ đọc file tạm, không gọi API.
7. Bật `RETRY_FAILED_SOURCES = True` trong cell retry để mở chu kỳ mới cho các
   source failed thuộc 10 ID đầu. Cell chạy nhánh arXiv với `limit=10`, giữ total
   attempts và cooldown, bỏ qua metadata/source đã complete hợp lệ.
8. Sau lần thử, đặt lại toggle False. Kiểm tra status và các mã lỗi mới.
9. Stop giữa phiên rồi resume `limit=10`; kiểm tra file/checksum và tổng attempts.
   Chỉ dùng `takeover_stale=True` khi chắc chắn runtime cũ đã ngừng.
10. Sau smoke/interrupt check đạt, có thể chủ động chạy full range qua CLI hoặc
    `await run_pipeline(config, {'arxiv','s2'}, resume=True, limit=None)`.

Bật anonymous khi chưa có key: `execution.allow_anonymous_s2: true` (config mẫu).
Env `SEMANTIC_SCHOLAR_API_KEY` ưu tiên hơn Secrets. 401/403 dừng dịch vụ tương ứng,
không tự hạ xuống anonymous. Anonymous pacing là chính sách bảo thủ của dự án.

## CLI từ project root

```bash
PYTHONPATH=src python -m crawler.cli init
PYTHONPATH=src python -m crawler.cli run --limit 10
PYTHONPATH=src python -m crawler.cli status
PYTHONPATH=src python -m crawler.cli diagnose
PYTHONPATH=src python -m crawler.cli retry-failed --limit 10 --stages arxiv
PYTHONPATH=src python -m crawler.cli resume --limit 10 --stages arxiv
PYTHONPATH=src python -m crawler.cli export --run-id export-001
```

CLI `retry-failed` chỉ reset failed stages của service được chọn, không gọi mạng.
Notebook có lựa chọn source-only. `recheck-not-found` riêng cho not_found.
`refresh-discovery --limit 10` và `refresh-references --limit 10` mở snapshot mới,
giữ history; không tự refresh khi resume. `run`/`resume` không có `--limit` chọn
cả 5.000 ID. Notebook smoke luôn truyền 10; không auto chạy full range.

Các lệnh mutation/export dùng chung local lock và active marker. Local lock
không phải distributed lock trên Drive: chỉ một notebook/process ghi dataset.
Redirect chỉ được theo trên cùng HTTPS service host và vẫn đi qua pacing/budget;
redirect sang host khác ghi `redirect_disallowed`, không âm thầm dùng main site.

## API và phạm vi

- https://info.arxiv.org/help/api/user-manual.html
- https://info.arxiv.org/help/api/tou.html
- https://info.arxiv.org/help/mimetypes.html
- https://api.semanticscholar.org/api-docs/graphs
- https://www.python-httpx.org/quickstart/

Code repo và Drive runtime độc lập; parsing, matching, Jupyter Book, GitHub Pages,
upload dataset và report repo thuộc milestone sau. Chưa chạy toàn bộ 5.000 ID.

## Discovery batching

`network.discovery_batch_size` mặc định 50 (1–50), giới hạn thêm bởi
`execution.queue_capacity`. Pipeline luân phiên một batch discovery và một
version stage; metadata riêng từng version và source vẫn qua cùng scheduler.
Batch chỉ gom các ID đang pending/running có cùng cycle-attempt count. Mỗi
request tiêu thụ một attempt của từng ID tham gia, checkpoint cả nhóm một lần
trước khi gửi; không reset attempts khi chia/gom batch hoặc restart. Nhóm có
attempts khác nhau được xử lý riêng để mỗi ID giữ tối đa ba attempts/chu kỳ.

Atom error, ID ngoài batch, duplicate hoặc response có totalResults không khớp
không được biến thành not_found. Raw response và request ID list được lưu với
mỗi discovery result. Recovery tái tạo version rows từ marker nếu runtime chết
trước terminal checkpoint. Metrics ghi danh sách jobs của batch, chỉ cộng thời
gian request một lần.

`papers.csv`/`versions.csv` là views có thể trễ tối đa 49 terminal mutations;
`jobs.csv` vẫn checkpoint mỗi request hoặc terminal batch. Dùng CLI status hoặc
`status_counts()` khi đang chạy. Views được flush ở cuối phiên và reconcile.

Notebook `5000_crawl.ipynb` mặc định smoke 10 ID. Muốn dùng SSD, notebook tạo
project path tương đối `scratch` là symlink đến thư mục tạm do hệ điều hành cấp;
config/log không lưu mount path hoặc đường dẫn SSD tuyệt đối. Khi runtime reset,
link hỏng được tạo lại, staging dở tải lại từ đầu, kết quả complete nằm trên Drive.
Sau cập nhật code cần restart kernel trước khi import lại crawler. Chỉ bật
`RUN_FULL_RANGE=True` sau khi smoke mới và interrupt/resume đã đạt.
