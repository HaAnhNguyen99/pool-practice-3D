# pool_cv: đo thế bi từ video thi đấu

Python thuần, không cần numpy/opencv; chỉ cần `ffmpeg`/`ffprobe`.

## Tự động: bắt cú đánh trong cả trận (khuyên dùng)

```
cd tools/pool_cv
python shotscan.py "../../Training clips/<video>.mp4"                       # tự hiệu chỉnh camera
python shotscan.py "../../Training clips/<video>.mp4" --calib ../../calib/usopen2023-final.json   # dùng camera có sẵn
```

1. **Hiệu chỉnh:** lấy ~40 khung rải đều, giữ khung camera đầu bàn sạch, lấy trung vị 5 đường mép rồi khớp camera (`tablefind.py`). Không cần vùng quét cố định, nên chạy được cho giải khác.
2. **Quét nhanh:** 2 khung/giây ở 640×360. Mỗi khung: có phải camera trên cao không, rồi dò bi thô. Lưu đệm ở `scan_out/<video>/signals/` theo đoạn 10 phút; dừng giữa chừng vẫn chạy tiếp được. Video 2,5 giờ mất khoảng 10–15 phút.
3. **Sự kiện:** tìm các thế bi đứng yên, so hai thế liên tiếp để biết bi nào vào lỗ. Cảnh phát lại bị bỏ qua. Cú kết thúc ván được nhận ra khi thế sau là ván mới. Lỗ được theo dõi qua đường lăn của bi.
4. **Đo chính xác:** lấy trung vị trên tối đa 4 khung full-res trước cú đánh, dùng `balls.py`.
5. **Duyệt:** mở `scan_out/<video>/report.html` (ảnh trước/sau, vòng đánh dấu bi, θ, lỗ, độ tin cậy, ghi chú). Sau đó:

```
python cut_shots.py "../../scan_out/<video>/shots.json" --min-conf high --player "Tên cơ thủ"
python cut_shots.py "../../scan_out/<video>/shots.json" --ids ID1,ID2
```

### Kiểm tra cú có thật sự vào lỗ (bảng điểm)

```
python turncheck.py "../../scan_out/<video>/shots.json"
python cut_shots.py "../../scan_out/<video>/shots.json" --min-conf medium --verified
```

`turncheck.py` đọc mũi tên lượt đánh trên bảng điểm từ trước cú đánh tới lúc cú kế tiếp bắt đầu:
- **ok:** vẫn lượt của người đánh. Bi vào lỗ, người đánh được đánh tiếp.
- **reject:** trong 15 s sau cú đánh, lượt chuyển sang đối thủ. Nghĩa là trượt, đánh phòng thủ hoặc phạm lỗi.
- **unknown:** không đọc được bảng điểm, cú kết thúc ván, hoặc lượt đổi quá muộn nên có thể do cú sau.

Kết quả ghi vào trường `turn` của `shots.json`:
- `cut_shots.py` luôn bỏ cú `reject`; dùng `--force` để vẫn cắt.
- `--verified` chỉ cắt cú `ok`.
- Tên cơ thủ lấy từ `turn.shooter`.

Bảng điểm hỗ trợ:
- **World Nineball Tour 2023** (US Open, European Open): học mẫu mũi tên từ poster các clip đã có tên.
- **Premier League Pool 2024:** đọc trực tiếp mũi tên trắng trên thanh đỏ.

Giải mới cần thêm toạ độ vùng bảng điểm.

Clip bị loại được chuyển sang `clips/_rejected/`, ghi lý do trong `rejected.json`.

### Premier League Pool 2024

Bàn băng sáng. Bảng điểm đè lên băng gần, nên mép dưới phát hiện được là mép ngoài băng (x=−8) chứ không phải mũi băng. Camera đã kiểm chứng nằm ở `calib/premierleague2024.json`: tâm 2 lỗ giữa và lưới bàn khớp ảnh.

```
python shotscan.py "../../Training clips/Shane Van Boening vs Ko Pin Yi_2024 Premier League Pool.mp4" --calib ../../calib/premierleague2024.json
```

### WPA 10-Ball World Championship 2025

Nỉ xanh dương, mặt băng cùng màu nỉ, không có vạch phấn foot string. Màu nỉ ghi trong trường `cloth` của file hiệu chỉnh; `shotscan` và `tablefind` đọc trường này. Camera đầu bàn ở xa (bi ≈ 11–17 px), nên khung quét nhanh dùng màu nền riêng cho từng hàng ảnh.

Camera đo trên ảnh trung vị 6 khung, lưu ở `calib/wpa2025-10ball.json`. Kiểm chứng: các đường y=12.5/25/37.5 trùng 3 kim cương trên băng gần, đường x=50 đi qua 2 lỗ giữa.

```
python shotscan.py "../../Training clips/Joshua Filler vs Dương Quoc Hoang last 32 - wpa 10 ball 2025.mp4" --calib ../../calib/wpa2025-10ball.json
python rackcheck.py "../../scan_out/<trận>/shots.json"
python cut_shots.py "../../scan_out/<trận>/shots.json" --min-conf low --verified
```

Bảng điểm WPA không có mũi tên lượt đánh, nên dùng `rackcheck.py` thay cho `turncheck.py`:
- **Cú cuối ván** (chỉ còn bi cái và bi 10): tỉ số của một cơ thủ phải tăng trong 40 s sau khung trước cú đánh, và bi 10 không được dừng ở chỗ khác trước đó. Hàng tỉ số tăng cho biết ai đánh.
- **Cú giữa ván:** so khung full-res trước cú đánh với khung camera đầu bàn sau đó. Số bi phải giảm đúng 1 và chỗ cũ của bi mục tiêu phải trống. Cách này không biết ai đánh, nên tên cơ thủ để trống.

Rà bằng hình trên trận Filler – Dương Quốc Hoàng: `rackcheck` cho 30 cú ok, trong đó 7 cú sai bị loại khi soát (còn 23). 5 cú do nhận nhầm bi cái hoặc bi mục tiêu. 1 cú có hai bi cùng biến mất. 1 cú vị trí đo không ổn định. Thêm 2 cú sai lỗ (lỗ theo dõi tự động). Vì vậy vẫn nên xem ảnh trước/sau của từng cú trước khi cắt.

#### Camera nhìn thẳng từ trên xuống (trận Dương Quốc Hoàng – Aloysius Yapp)

Một số trận WPA 2025 dùng camera treo thẳng trên bàn thay cho camera đầu bàn. File hiệu chỉnh `calib/wpa2025-10ball-top.json` có thêm các trường sau:
- `view: "top"`
- `rail_ref`: màu băng, để loại các camera khác cũng thấy nỉ xanh.
- `board`: vùng tỉ số; bảng điểm có 5 cột set, so cả hàng.

Hiệu chỉnh bằng cách khớp 4 đường mũi băng trên ảnh trung vị 7 khung (rms 0.44 px). Khi camera gần như vuông góc với mặt bàn thì Z và f không tách riêng được, nhưng ánh xạ mặt bàn vẫn đúng: kim cương trên 4 băng lệch ≤ 2 px. Hệ toạ độ: x=0 là băng ngắn bên trái ảnh, y=0 là băng dài phía trên.

Khác biệt khi `view` là `top`:
- **Không dịch tâm bi xuống** khi quét. Phép dịch đó chỉ dùng để bù bóng đổ ở camera đầu bàn.
- **Phân biệt bi sọc với bi cái.** Nhìn từ trên xuống, bi 9 và bi 10 có lúc chỉ lộ phần trắng. Cách phân biệt là đếm tỉ lệ điểm ảnh không trắng trong đĩa 0.9r: bi cái khoảng 0.02 (vài chấm), bi sọc từ 0.12 trở lên. Ngưỡng là `NW_SCAN` khi quét và `NW_FULL` ở full-res (trường `nw` của `balls.detect`).
- **Phân loại màu bi trên nỉ xanh dương** (khi có `cloth`): bi đen ám xanh vẫn ra "đen", và bi xanh lá không bị nhầm thành xanh dương.

```
python shotscan.py "../../Training clips/Dương Quốc Hoàng vs Aloysius Yapp - 2025.mp4" --calib ../../calib/wpa2025-10ball-top.json
python rackcheck.py "../../scan_out/Dương Quốc Hoàng vs Aloysius Yapp - 2025/shots.json"
python cut_shots.py "../../scan_out/Dương Quốc Hoàng vs Aloysius Yapp - 2025/shots.json" --ids ... --event "WPA 10-Ball World Championship 2025"
```

`clips/clips.json` là nguồn dữ liệu; `clips/clips.js` được sinh lại tự động, không sửa tay. Chạy lại không tạo trùng.

Độ tin cậy:
- **Cao:** lỗ theo dõi được và bi đứng yên.
- **Vừa:** chỉ có một lỗ hợp lý.
- **Thấp:** nên xem kỹ trước khi cắt.

Tool không tự nhận ra ai đánh; dùng `--player` hoặc sửa `clips.json`.

Kiểm thử trên clip 1 (`--calib usopen2023-final.json`): bắt đủ 4 cú. θ khớp số đo tay trong khoảng 0.1°: 16.4 / 24.6 / 43.8 / 5.9. Cú bi 3 không có khung trên cao nên bị bỏ qua, và cảnh phát lại không bị tính là cú mới.

## Thủ công: quy trình cho một clip mới

1. **Tìm cú đánh.** Dùng `ffmpeg ... select='gt(scene,0.3)',showinfo` để lấy các mốc chuyển cảnh. Sau đó dựng contact sheet 1 fps có timestamp. Với mỗi cú, cần một khung **camera trên cao** chụp sau khi bi lần trước đã dừng và trước khi cơ thủ đánh. Các đoạn replay nằm giữa hai lần logo chuyển cảnh, không tính là cú mới.
2. **Kiểm tra camera.** Xuất một khung trên cao sạch, không có người che băng, ra PPM (`-pix_fmt rgb24 -c:v ppm`), rồi chạy `python calibrate.py f.ppm --ref ../../calib/<event>.json`. Lệnh này in ra 5 đường thẳng mới cạnh giá trị tham chiếu. Lệch không quá ~2 px thì dùng lại camera cũ. Lệch nhiều hơn thì chạy `python calibrate.py f.ppm ../../calib/<new>.json` để khớp lại. Các vùng quét trong `calibrate.py` và `edges.py` được chỉnh cho khung hình US Open 2023; với khung hình khác cần sửa hằng số ở đầu file.
3. **Đo bi.** Chạy `balls.py f.ppm calib/<event>.json`. Tâm bi bằng tia camera qua tâm đường tròn, giao với mặt phẳng z=−1.125. Nếu bi cái bị tay hoặc cơ che, đặt điểm khởi đầu bằng tay rồi gọi `balls.refine`.
4. **Tính góc.** `geom.theta(cb, ob, pocket)` là bản chuyển nguyên văn `geom()` của `index.html`. Lấy lỗ theo chỗ bi thực sự rơi trong video. Bi sát băng (đo được < 1.125) thì đặt bằng 1.125.
5. **Cắt clip.** Re-encode 720p (`-crf 22 -movflags +faststart`, giữ tiếng), poster là khung trên cao trước cú đánh. Ghi vào `clips/clips.js`.

## Hệ toạ độ

Đơn vị inch, bàn 9 ft là 100×50. x=0 là băng gần camera, y=0 là băng trái trong ảnh. Cùng hệ với `index.html`, nên lỗ 0=(0,0), 3=(0,50) là hai lỗ góc gần camera.

## Bẫy đã gặp

- Mép sáng ở mép dưới ảnh (y≈879) là mép ngoài mặt trên đệm gần, **không** phải x=0.
- Cụm chấm trắng trên nỉ không có tâm ở head spot. Head spot là chấm ở px (960.3, 738.8).
- Nửa dưới bi trắng gần màu nỉ, nên bi cái bắt buộc phải qua bước khớp bán kính cố định.
