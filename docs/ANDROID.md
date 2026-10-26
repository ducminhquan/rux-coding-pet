# Android và RobotSDK

Build bằng scripts/build.sh với JDK 17, Android SDK platform 35/build-tools 35.0.0.
Ứng dụng min SDK 26, target 28; thiết bị đã thử Android 11. Không cần Gradle.
Nhập vendor/RobotSdk-release.aar và các WAV trước khi build; xem README chính.

## Preset

scripts/active_scenario.json có schema version 1, voice và năm state:
working, attention, completed, idle, failed. Mỗi state có face, motion, motion2,
ears, angle, repeat. motion/motion2: 0–80; 0 bỏ qua. ears: 0–2 trong preset chat;
preview cho phép 3. angle: 1–45 độ. repeat: 0 hoặc 20–300 giây.

Hai hành động chạy tuần tự, một nhịp, tối đa 3 giây mỗi bước; motor-off và nghỉ
200 ms giữa bước. Bước 2 có thể bù chuyển động nhưng không đo/đảm bảo về đúng vị trí.
Radar 1 ra trước rồi về, 2 ra sau rồi về, 3 trước → sau → về. Không dùng góc 0 để
đứng yên vì SDK có thể đổi nó thành 90; dùng ears=0.

Chọn kịch bản phù hợp chỗ đặt robot. Stop và callback sensor chặn bước còn lại;
firmware radar có thể hoàn thành nhịp ngắn đã nhận. Các test nguồn không điều khiển
motor; kiểm tra trên robot là bước riêng.

## Debug

```sh
adb -s ROBOT_SERIAL logcat -s RuxAssistant AndroidRuntime
python3 scripts/rux.py status
python3 scripts/rux.py stop
```

ACK set-state/session-state chỉ là chấp nhận trạng thái; xem RUN_START,
STEP_MOTOR_OFF, MOTOR_OFF, RUN_FINISHED và AUDIO_STARTED/AUDIO_DONE để biết tiến
trình SDK. Log không thay cho phản hồi quan sát/nghe thực tế.

App dùng MediaPlayer USAGE_ASSISTANT; âm lượng và tuyến loa tùy firmware. File
completed của bản triển khai gốc đã tăng 5 dB, không clipping; bản source không
kèm WAV, mức âm thực tế phụ thuộc file bạn nhập. App không ép âm lượng hệ thống.

Voice preview, Stop, cấu hình và chọn phiên đều qua ADB đã được cấp quyền. Không có
root, unlock bootloader, flash firmware hay factory reset trong script build/cài.
