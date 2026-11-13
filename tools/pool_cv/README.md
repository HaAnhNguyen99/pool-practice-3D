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
