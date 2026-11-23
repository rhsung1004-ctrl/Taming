// 어둡고 반사되는 늪·호수 물 (URP 6000.0). 텍스처 없이 전부 절차적으로 그린다.
//  - 잔물결 법선: 값 노이즈(해석적 미분) 여러 겹 + 긴 너울 두 줄기
//  - 프레넬 반사: 하늘 꼭대기 색(_SkyTopColor) ~ 지평선 색. 지평선 색은 안개 색(unity_FogColor)을 그대로 쓴다
//    (룩 도구가 안개 색 = 하늘 지평선 색으로 맞추므로 분위기 프리셋을 바꿔도 물빛이 따라간다)
//  - 달빛 반짝임: 달 방향(주광)으로 좁은 하이라이트 + 넓은 달길 + 반짝이는 점, 등불 같은 추가 광원도 물에 비친다
//  - 깊이 텍스처가 있으면 물가가 옅어지고 희미한 물거품이 생긴다. 없으면(또는 값이 이상하면) 그냥 깊은 물로 그린다
//
// 불투명 / 투명 선택: 투명 큐(Transparent-100) + ZWrite On 으로 그린다.
//   물가를 옅게 하려면 불투명 물체의 깊이(_CameraDepthTexture)를 읽어야 하는데, URP는 깊이를 불투명 패스가 끝난 뒤에
//   복사한다 (렌더러의 Depth Texture Mode = After Opaques. 'URP 설정 맞추기' 도구가 맞춘다). 불투명 큐에서는 이번 프레임
//   깊이를 읽을 수 없으므로 투명 큐여야 한다. 큐를 Transparent-100 으로 두어 다른 투명 물체(안개·불티 입자)보다 항상 먼저
//   그려지게 하면 거리 정렬이 큐 순서에 묻혀 정렬 문제가 생기지 않는다. ZWrite On 이라 물 아래 입자가 물 위로 비치지 않는다.
Shader "Necro/Water"
{
    Properties
    {
        [Header(Color)]
        _DeepColor ("깊은 물 색", Color) = (0.015, 0.02, 0.045, 1)
        _ShallowColor ("얕은 물 색", Color) = (0.05, 0.07, 0.1, 1)
        _SkyTopColor ("비치는 하늘 꼭대기 색", Color) = (0.03, 0.03, 0.09, 1)
        _ReflectionStrength ("반사 세기", Range(0, 2)) = 1
        _FresnelBias ("정면 반사 (0.02 = 실제 물)", Range(0, 0.5)) = 0.04
        _FresnelPower ("프레넬 지수", Range(1, 8)) = 4.5
        _Opacity ("불투명도", Range(0, 1)) = 0.9

        [Header(Waves)]
        _WaveScale ("잔물결 크기 (1/m, 클수록 잘게)", Float) = 0.45
        _WaveSpeed ("잔물결 속도", Float) = 0.35
        _WaveStrength ("잔물결 세기", Range(0, 2)) = 0.35
        _SwellDir ("너울 방향 (xz)", Vector) = (0.8, 0, 0.6, 0)
        _SwellStrength ("너울 세기", Range(0, 1)) = 0.12

        [Header(Moon)]
        _MoonSpecPower ("달 하이라이트 날카로움", Range(50, 3000)) = 900
        _MoonSpecStrength ("달 하이라이트 세기", Range(0, 20)) = 6
        _MoonGlintPower ("달길 넓이 (작을수록 넓게)", Range(4, 200)) = 40
        _MoonGlintStrength ("달길 세기", Range(0, 4)) = 0.7
        _SparkleScale ("반짝이 크기 (1/m)", Float) = 9
        _SparkleAmount ("반짝이 양", Range(0, 1)) = 0.25
        _SparkleStrength ("반짝이 세기", Range(0, 20)) = 8

        [Header(Lights)]
        _LightReflectPower ("등불 반사 날카로움", Range(8, 1000)) = 160
        _LightReflectStrength ("등불 반사 세기", Range(0, 10)) = 2

        // 1장 늪은 아주 얕다 (젖은 곳 수심 중앙값 약 0.37 m). 1.2 m / 0.35 m 이면 주인공 카메라 각도(약 25°)에서도
        // 늪 절반이 알파 0.64 아래로 옅어지고 물거품이 넓게 깔려, 물가만 옅어지도록 0.6 m / 0.18 m 로 둔다 (호수는 거의 차이 없음)
        [Header(Shore)]
        [ToggleUI] _UseDepth ("깊이 텍스처로 물가 옅게", Float) = 1
        _ShoreFade ("물가가 옅어지는 깊이 (m)", Float) = 0.6
        _DepthColorDistance ("얕은 색 → 깊은 색 깊이 (m)", Float) = 3
        _FoamWidth ("물거품 폭 (m)", Float) = 0.18
        [HDR] _FoamColor ("물거품 색", Color) = (0.35, 0.45, 0.6, 1)
    }

    SubShader
    {
        Tags { "Queue" = "Transparent-100" "RenderType" = "Transparent" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        Pass
        {
            Name "WaterForward"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile _ _FORWARD_PLUS
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            // 투명 표면: 화면 공간 그림자 대신 그림자 맵을 직접 읽는다
            #define _SURFACE_TYPE_TRANSPARENT 1

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _DeepColor;
                half4 _ShallowColor;
                half4 _SkyTopColor;
                half _ReflectionStrength;
                half _FresnelBias;
                half _FresnelPower;
                half _Opacity;
                float _WaveScale;
                float _WaveSpeed;
                half _WaveStrength;
                float4 _SwellDir;
                half _SwellStrength;
                half _MoonSpecPower;
                half _MoonSpecStrength;
                half _MoonGlintPower;
                half _MoonGlintStrength;
                float _SparkleScale;
                half _SparkleAmount;
                half _SparkleStrength;
                half _LightReflectPower;
                half _LightReflectStrength;
                half _UseDepth;
                float _ShoreFade;
                float _DepthColorDistance;
                float _FoamWidth;
                half4 _FoamColor;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float eyeDepth : TEXCOORD1;
                half fogFactor : TEXCOORD2;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionWS = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                o.eyeDepth = -TransformWorldToView(o.positionWS).z;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            // 격자점 해시 (격자 좌표를 1024 로 감아 큰 좌표에서도 정밀도를 지킨다)
            float WaterHash(float2 p)
            {
                p = p - 1024.0 * floor(p / 1024.0);
                p = frac(p * float2(0.1031, 0.1030));
                p += dot(p, p.yx + 33.33);
                return frac((p.x + p.y) * p.x);
            }

            // 값 노이즈와 해석적 미분: (값, d/dx, d/dy)
            float3 WaterNoiseD(float2 x)
            {
                float2 p = floor(x);
                float2 w = frac(x);
                float2 u = w * w * w * (w * (w * 6.0 - 15.0) + 10.0);
                float2 du = 30.0 * w * w * (w * (w - 2.0) + 1.0);
                float a = WaterHash(p);
                float b = WaterHash(p + float2(1, 0));
                float c = WaterHash(p + float2(0, 1));
                float d = WaterHash(p + float2(1, 1));
                float k1 = b - a, k2 = c - a, k4 = a - b - c + d;
                return float3(a + k1 * u.x + k2 * u.y + k4 * u.x * u.y,
                              du * float2(k1 + k4 * u.y, k2 + k4 * u.x));
            }

            // 물 높이의 기울기 (xz)
            float2 WaterSlope(float2 xz, float t)
            {
                float2 slope = 0;
                float scale = _WaveScale;
                float amp = 1.0;
                // 겹마다 방향을 돌리고 다른 쪽으로 흐르게 한다
                float2x2 rot = float2x2(0.8, -0.6, 0.6, 0.8);
                float2x2 back = float2x2(1, 0, 0, 1);    // = rot^k
                float2 q = xz;                            // = rot^k · xz
                float2 drift = float2(1.0, 0.35);
                [unroll] for (int k = 0; k < 4; k++)
                {
                    float3 n = WaterNoiseD(q * scale + drift * (t * _WaveSpeed * (1.0 + k * 0.6)));
                    // 노이즈 입력이 scale · rot^k · xz 이므로 xz 에 대한 기울기 = scale · (rot^k)ᵀ · ∇n  (행벡터로 g · rot^k)
                    float2 g = n.yz * (amp * scale);
                    slope += mul(g, back);
                    q = mul(rot, q);
                    back = mul(back, rot);
                    drift = float2(-drift.y, drift.x);
                    scale *= 2.1;
                    amp *= 0.42;
                }
                // 긴 너울 두 줄기
                float2 sd = normalize(_SwellDir.xz + float2(0.0001, 0));
                float2 sd2 = float2(-sd.y, sd.x) * 0.6 + sd * 0.8;
                float ph1 = dot(xz, sd) * 0.55 - t * 0.9;
                float ph2 = dot(xz, sd2) * 0.83 - t * 1.3;
                slope += sd * (cos(ph1) * 0.55 * _SwellStrength * 3.0) + sd2 * (cos(ph2) * 0.83 * _SwellStrength * 1.5);
                return slope;
            }

            half3 SkyReflection(float3 R)
            {
                // NecroSky 와 같은 꼴: 지평선 → 꼭대기 (지평선 번짐 0.55)
                half3 horizon = unity_FogColor.rgb;
                return lerp(horizon, _SkyTopColor.rgb, pow(saturate(R.y), 0.55));
            }

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);

                float t = fmod(_Time.y, 3600.0);
                float2 xz = i.positionWS.xz;
                float2 slope = WaterSlope(xz, t) * _WaveStrength;
                float3 N = normalize(float3(-slope.x, 1.0, -slope.y));
                float3 V = GetWorldSpaceNormalizeViewDir(i.positionWS);
                float NdotV = saturate(dot(N, V));

                // 물가: 이 픽셀 뒤의 불투명 물체까지 남은 깊이
                float waterDepth = 1000.0;
                if (_UseDepth > 0.5)
                {
                    float2 suv = GetNormalizedScreenSpaceUV(i.positionCS);
                    float sceneEye = LinearEyeDepth(SampleSceneDepth(suv), _ZBufferParams);
                    float diff = sceneEye - i.eyeDepth;
                    // 깊이 텍스처가 없거나 값이 이상하면 (물 앞의 물체보다 가까움) 깊은 물로 본다
                    if (diff > 0.0) waterDepth = diff;
                }
                half shore = saturate(waterDepth / max(_ShoreFade, 0.01));
                half deep = saturate(waterDepth / max(_DepthColorDistance, 0.01));

                // 반사
                half fresnel = _FresnelBias + (1.0 - _FresnelBias) * pow(1.0 - NdotV, _FresnelPower);
                float3 R = reflect(-V, N);
                R.y = abs(R.y);
                half3 sky = SkyReflection(R) * _ReflectionStrength;

                // 달빛
                float4 shadowCoord = TransformWorldToShadowCoord(i.positionWS);
                Light mainLight = GetMainLight(shadowCoord, i.positionWS, half4(1, 1, 1, 1));
                half shadow = mainLight.shadowAttenuation * mainLight.distanceAttenuation;
                half rDotL = saturate(dot(R, mainLight.direction));
                half moonSpec = pow(rDotL, _MoonSpecPower) * _MoonSpecStrength;
                half moonGlint = pow(rDotL, _MoonGlintPower) * _MoonGlintStrength;
                // 반짝이는 점: 칸마다 무작위 자리의 작은 점이 달길 안에서만 깜박인다
                float2 sp = xz * _SparkleScale;
                float2 cell = floor(sp);
                float2 dotPos = float2(WaterHash(cell + 5.17), WaterHash(cell + 11.3)) * 0.6 + 0.2;
                float dotMask = smoothstep(0.16, 0.0, length(frac(sp) - dotPos));
                float flick = WaterHash(cell + floor(t * 3.0 + WaterHash(cell) * 7.0) * 17.0);
                half sparkle = step(1.0 - _SparkleAmount, flick) * dotMask * pow(rDotL, _MoonGlintPower) * _SparkleStrength;
                half3 moonLight = mainLight.color * ((moonSpec + moonGlint * fresnel + sparkle) * shadow);

                // 물 자체 색: 어둡게. 주변광을 아주 조금 받는다
                half3 body = lerp(_ShallowColor.rgb, _DeepColor.rgb, deep);
                body *= (SampleSH(float3(0, 1, 0)) + mainLight.color * (0.15 * shadow));

                half3 color = lerp(body, sky, fresnel) + moonLight;

                // 등불 같은 추가 광원이 물에 비친다
                #if defined(_ADDITIONAL_LIGHTS)
                {
                    InputData inputData = (InputData)0;
                    inputData.positionWS = i.positionWS;
                    inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
                    uint lightCount = GetAdditionalLightsCount();
                    LIGHT_LOOP_BEGIN(lightCount)
                        Light l = GetAdditionalLight(lightIndex, i.positionWS, half4(1, 1, 1, 1));
                        half atten = l.distanceAttenuation * l.shadowAttenuation;
                        float3 H = normalize(l.direction + V);
                        half spec = pow(saturate(dot(N, H)), _LightReflectPower) * _LightReflectStrength;
                        color += l.color * (atten * (spec + 0.04 * saturate(dot(N, l.direction))));
                    LIGHT_LOOP_END
                }
                #endif

                // 물가의 희미한 물거품 (잔물결 따라 끊긴다)
                half foamMask = 1.0 - saturate(waterDepth / max(_FoamWidth, 0.01));
                half foamNoise = WaterNoiseD(xz * 3.0 + slope * 4.0 + t * 0.2).x;
                half foam = foamMask * smoothstep(0.35, 0.75, foamNoise + foamMask * 0.3) * shore;
                color = lerp(color, _FoamColor.rgb * (0.4 + 0.6 * shadow), foam * 0.8);

                half alpha = saturate(_Opacity + fresnel * 0.5) * shore;
                alpha = max(alpha, foam * 0.8);

                // 안개 값을 half 에 먼저 담는다 (MixFog(half3, float) 은 half·float 오버로드 사이에서 모호한 호출이 될 수 있다)
                half fogCoord = (half)InitializeInputDataFog(float4(i.positionWS, 1.0), i.fogFactor);
                color = MixFog(color, fogCoord);
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }

    FallBack "Hidden/Universal Render Pipeline/FallbackError"
}
