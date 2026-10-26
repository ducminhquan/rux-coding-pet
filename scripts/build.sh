#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BT="$SDK/build-tools/35.0.0"
JAR="$SDK/platforms/android-35/android.jar"
mkdir -p build/classes build/dex
python3 scripts/scenario.py bundle
rm -f build/classes/com/rux/assistant/*.class
unzip -p vendor/RobotSdk-release.aar classes.jar > build/robotsdk.jar
javac -source 8 -target 8 -classpath "$JAR:build/robotsdk.jar" -d build/classes android/src/com/rux/assistant/*.java
jar cf build/app.jar -C build/classes .
"$BT/d8" --lib "$JAR" --min-api 26 --output build/dex build/app.jar build/robotsdk.jar
"$BT/aapt" package -f -0 wav -A android/assets -M android/AndroidManifest.xml -I "$JAR" -F build/unsigned.apk
(cd build/dex && zip -q -u ../unsigned.apk classes.dex)
"$BT/zipalign" -f 4 build/unsigned.apk build/aligned.apk
if [ ! -f build/debug.keystore ]; then
 keytool -genkeypair -keystore build/debug.keystore -storepass android -keypass android -alias rux-debug -dname 'CN=Rux Local Development' -keyalg RSA -validity 3650 >/dev/null 2>&1
fi
"$BT/apksigner" sign --v4-signing-enabled false --ks build/debug.keystore --ks-pass pass:android --out build/rux-assistant.apk build/aligned.apk
"$BT/apksigner" verify build/rux-assistant.apk
rm -f build/rux-assistant.apk.idsig
