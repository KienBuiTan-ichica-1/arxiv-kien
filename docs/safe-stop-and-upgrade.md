# Dừng crawler, sao lưu và nâng cấp khi Drive còn đồng bộ

Áp dụng cho một notebook đang chạy crawler trên dataset hiện có. Các bước dưới
đây không tự sửa dữ liệu trên Drive và không yêu cầu xóa progress/cooldown.

## 1. Dừng có checkpoint

1. Bấm Stop một lần ở cell pipeline và chờ cell hết trạng thái đang chạy.
2. Nếu hiện CancelledError/KeyboardInterrupt do thao tác dừng, đó chưa tự chứng
   minh dữ liệu lỗi; pipeline có finally để checkpoint và đóng metrics/log.
3. Chưa chọn Restart session, Disconnect and delete runtime, đổi tài khoản hoặc
   tắt máy ảo. Giữ phiên hiện tại cho đến khi sao lưu/kiểm tra xong.
4. Nếu Stop không hoàn tất hoặc xuất hiện lỗi ghi/IO, không xóa lock/marker để
   chạy phiên khác. Giữ nguyên runtime và ghi lại traceback để chẩn đoán.

Stop không bảo đảm Google Drive đã upload xong mọi thay đổi. Việc kiểm tra local
mount và việc đọc được cùng byte từ Drive connector là hai bước khác nhau.

## 2. Giữ bản sao ngoài mounted Drive

Chạy cell sau **chỉ sau khi crawler đã dừng**. Cell tạo ZIP trên đĩa tạm của VM,
bao gồm toàn bộ runtime. Nó có thể tốn thời gian nếu dataset có nhiều file nhỏ.
Không đặt ZIP bên trong runtime vì sẽ tự đưa file backup vào chính archive.

```python
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import zipfile
import hashlib
from google.colab import files

runtime_root = Path(config.paths['persistent_root'])
assert runtime_root.is_dir()
backup_dir = Path(tempfile.mkdtemp(prefix='arxiv-runtime-backup-'))
backup_zip = backup_dir / (
    'runtime-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.zip'
)
with zipfile.ZipFile(backup_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in runtime_root.rglob('*'):
        if path.is_file():
            archive.write(path, arcname=path.relative_to(runtime_root.parent).as_posix())
with zipfile.ZipFile(backup_zip) as archive:
    assert archive.testzip() is None, 'Backup ZIP CRC check failed'
hash_ = hashlib.sha256()
with backup_zip.open('rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        hash_.update(chunk)
print('Backup bytes:', backup_zip.stat().st_size)
print('Backup SHA-256:', hash_.hexdigest())
files.download(str(backup_zip))
```

Đợi trình duyệt tải xong ZIP về máy cá nhân trước khi bỏ runtime. File ZIP chỉ
nằm trên SSD Colab mà chưa tải về máy vẫn có thể mất khi runtime bị xóa.

Tối thiểu cần giữ toàn bộ progress để không mất attempts/cooldown, nhưng chỉ có
progress chưa bảo vệ source/data chưa đồng bộ. Vì vậy ưu tiên backup toàn runtime.

## 3. Kiểm tra progress trong runtime hiện tại

```python
from crawler.progress import ProgressStore

store = ProgressStore(config.paths['persistent_root'])
print(store.status_counts())
```

Nếu báo snapshot/journal không khớp hoặc thiếu record, giữ backup và traceback;
không sửa sequence, checksum, xóa journal hoặc tạo dataset rỗng để chạy tiếp.

Kiểm tra active marker còn hay không:

```python
from pathlib import Path
print('Active marker còn:', (
    Path(config.paths['persistent_root']) / 'progress' / 'active_run.json'
).exists())
```

Marker không còn chỉ cho biết bước dọn lock đã chạy; nó không chứng minh
checkpoint/finalization thành công, vì lock vẫn được dọn nếu ghi snapshot bị lỗi.
Phải kiểm tra traceback và load/validate progress thành công trước khi coi phiên
đã dừng an toàn. Nó cũng không chứng minh mọi file đã đồng bộ lên cloud.
Ngược lại, marker còn có thể là dấu phiên bị ngắt;
chỉ takeover sau khi chắc chắn phiên ghi cũ đã ngừng.

## 4. Đối chiếu bản trên Drive

Có thể so sánh bản Drive sau đồng bộ với ZIP/local mount theo checksum, row count
và journal sequence. Cần giữ nguyên cả jobs.csv, journal, checksum và backups.
Không lấy snapshot ở một thời điểm ghép với journal cũ hơn rồi kết luận dataset
đã hỏng khi crawler/FUSE vẫn còn cập nhật.

Trong tình huống cloud snapshot khai báo sequence cao hơn journal tải về, chưa
thể bảo đảm restart từ bản cloud đó. Giữ runtime hoặc bản ZIP local đã tải về máy
cho đến khi xác nhận cloud đã theo kịp. Không có một thời gian chờ cố định bảo
đảm Drive đồng bộ xong.

## 5. Cập nhật code và tiếp tục

1. Chỉ cập nhật sau khi đã giữ bản sao an toàn và biết bản progress dùng để resume
   là nhất quán. Bản hỗ trợ nhiều tháng không đổi schema progress.
2. Push commit mới lên GitHub, chạy cell git pull của notebook.
3. Restart session nếu crawler đã import. Mount Drive lại khi cần, chọn đúng
   project root cũ, chạy lại setup/config/Secrets và scratch SSD.
4. Với dataset đang cào dở, giữ nguyên range và persistent_root. Bộ sinh range
   cùng tháng mới vẫn tạo đúng danh sách ID cũ.
5. Chạy lại cell full range với resume=True. Các kết quả có marker/checksum hợp
   lệ được dùng lại, failed không tự retry.
6. TAKEOVER_STALE mặc định False. Chỉ True khi có marker cũ và phiên ghi trước
   đã dừng hoàn toàn. Không dùng flag để cho hai notebook cùng ghi dataset.

## 6. Range của các thành viên khác

Xem README để khai báo start_month/start_id/end_month/end_id và monthly_end_ids.
Với dataset mới độc lập, chọn persistent_root mới; không trộn range của thành
viên khác vào progress đang chạy của bạn. Bộ sinh ID không tự biết tháng có bao
nhiêu bài và không tự tra lịch sử arXiv để điền giới hạn tháng.
