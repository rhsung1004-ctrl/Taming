using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Necro.Proto
{
    // 프로토타입에서 F2로 켜고 끄는 '애니풍 룩 미리보기'.
    // 도형 캐릭터에 본편 툰 셰이더(Necro/Toon)를 입히고, 밤하늘·번지는 빛·색 보정을 켠다.
    // 룩 확정 단계의 셰이더가 실제 전투 화면에서 어떻게 보이는지 확인하는 용도.
    public static class ProtoLook
    {
        public static bool On;

        static Material sky;
        static GameObject volumeGo;
        static readonly Color Dusk = new Color(0.1f, 0.09f, 0.17f);

        public static void Reset()
        {
            On = false;
            sky = null;
            volumeGo = null;
        }

        public static void Toggle(Camera cam)
        {
            if (!On)
            {
                var toon = Shader.Find("Necro/Toon");
                if (toon == null || !toon.isSupported)
                {
                    Hud.Toast("툰 셰이더(Necro/Toon)를 쓸 수 없어요. Console의 셰이더 에러를 확인해 주세요.", 5f);
                    return;
                }
            }
            On = !On;
            Util.SetToon(On);

            // 하늘
            if (On)
            {
                if (sky == null)
                {
                    var sh = Shader.Find("Necro/Sky");
                    if (sh != null)
                    {
                        sky = new Material(sh);
                        sky.SetColor("_HorizonColor", Dusk);
                        sky.SetColor("_BottomColor", Dusk);
                        if (RenderSettings.sun != null)
                        {
                            Vector3 d = -RenderSettings.sun.transform.forward;
                            sky.SetVector("_MoonDir", new Vector4(d.x, d.y, d.z, 0f));
                        }
                    }
                }
                if (sky != null)
                {
                    RenderSettings.skybox = sky;
                    cam.clearFlags = CameraClearFlags.Skybox;
                }
            }
            else cam.clearFlags = CameraClearFlags.SolidColor;

            // 후처리
            if (On && volumeGo == null)
            {
                volumeGo = new GameObject("ProtoLookVolume");
                var vol = volumeGo.AddComponent<Volume>();
                vol.isGlobal = true;
                vol.priority = 20f;
                var profile = ScriptableObject.CreateInstance<VolumeProfile>();
                var bloom = profile.Add<Bloom>(true);
                bloom.threshold.Override(0.95f);
                bloom.intensity.Override(1.1f);
                bloom.scatter.Override(0.72f);
                var tone = profile.Add<Tonemapping>(true);
                tone.mode.Override(TonemappingMode.Neutral);
                var color = profile.Add<ColorAdjustments>(true);
                color.postExposure.Override(0.2f);
                color.contrast.Override(12f);
                color.saturation.Override(10f);
                var split = profile.Add<SplitToning>(true);
                split.shadows.Override(new Color(0.42f, 0.34f, 0.62f));
                split.highlights.Override(new Color(0.58f, 0.62f, 0.72f));
                var vig = profile.Add<Vignette>(true);
                vig.intensity.Override(0.28f);
                vol.profile = profile;
            }
            if (volumeGo != null) volumeGo.SetActive(On);
            var data = cam.GetUniversalAdditionalCameraData();
            if (data != null && On) data.renderPostProcessing = true;

            Hud.Toast(On ? "애니풍 룩 미리보기 켜짐 (F2로 끄기) — 툰 셰이더·외곽선·밤하늘·번지는 빛" : "애니풍 룩 미리보기 꺼짐", 4f);
        }
    }
}
