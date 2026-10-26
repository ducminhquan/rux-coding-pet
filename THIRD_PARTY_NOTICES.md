# Third-party components and local assets

This source export does not bundle third-party SDK binaries, firmware/resource
APKs, voice recordings, Android build tools, signing keys or account data.

- RobotSDK: manufacturer Letianpai. Obtain RobotSdk-release.aar from
  https://github.com/Letianpai-Robot/DemoForRobotSDK/tree/main/app/libs
  and follow the manufacturer's terms. SDK reference:
  https://cn.letianpai.com/?p=5915
- Native expression videos: optional GeeUIResource.apk taken from the owner's
  robot for local preview. The APK and extracted videos stay under ignored build/.
- Voice metadata: scripts/voices.json documents the provider/demo sources of the
  original local voice choices. The corresponding WAV recordings are not shipped.
- Python, JDK and Android SDK are installed separately under their own licenses.

Project source and host plugins are distributed under the MIT License in LICENSE,
as selected for the repository. This does not relicense manufacturer SDKs,
firmware, resource APKs, voice recordings or other third-party components.
