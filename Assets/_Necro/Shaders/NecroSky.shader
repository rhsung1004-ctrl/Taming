// 다크 판타지 밤하늘 (스카이박스). 텍스처 없이 전부 절차적으로 그린다.
//  - 위에서 지평선으로 번지는 색, 별 (성운 띠 안은 더 촘촘하게), 드물게 색이 있는 큰 별
//  - 보랏빛 성운 띠 (은하수처럼 하늘을 가로지르는 띠, 먼지 줄무늬), 지평선 위로 드리운 오로라 커튼
//  - 천천히 흐르는 얇은 구름 띠 (달 가까이는 은빛으로 빛난다)
//  - 달 표면 무늬 (바다·운석 구덩이), 달무리, 가끔 떨어지는 별똥별
// 지평선 색(_HorizonColor)은 안개 색과 같게 맞춰야 먼 땅이 하늘에 자연스럽게 녹아든다.
// 기존 속성 이름(_TopColor ~ _MoonGlow)은 LookPresetCycler 가 쓰므로 바꾸지 않는다.
Shader "Necro/Sky"
{
    Properties
    {
        _TopColor ("하늘 꼭대기 색", Color) = (0.02, 0.02, 0.07, 1)
        _HorizonColor ("지평선 색 (안개 색과 같게)", Color) = (0.16, 0.12, 0.27, 1)
        _BottomColor ("지평선 아래 색", Color) = (0.05, 0.04, 0.09, 1)
        _HorizonSharpness ("지평선 번짐 (작을수록 넓게)", Range(0.2, 3)) = 0.55
        _StarDensity ("별 밀도", Range(0, 0.2)) = 0.045
        _StarBrightness ("별 밝기", Range(0, 4)) = 1.4
        _MoonDir ("달 방향 (도구가 달빛 방향으로 맞춤)", Vector) = (0.4, 0.6, 0.5, 0)
        [HDR] _MoonColor ("달 색", Color) = (1.5, 1.6, 2.2, 1)
        _MoonSize ("달 크기", Range(0.005, 0.2)) = 0.045
        _MoonGlow ("달무리 세기", Range(0, 2)) = 0.5

        [Header(Moon Surface)]
        _MoonDetail ("달 표면 무늬 세기", Range(0, 1)) = 0.7

        [Header(Clouds)]
        _CloudColor ("구름 그늘 색", Color) = (0.045, 0.04, 0.08, 1)
        [HDR] _CloudLitColor ("달빛 받은 구름 색", Color) = (0.5, 0.5, 0.72, 1)
        _CloudCoverage ("구름 양", Range(0, 1)) = 0.5
        _CloudOpacity ("구름 진하기", Range(0, 1)) = 0.85
        _CloudScale ("구름 크기 (클수록 잘게)", Range(0.2, 8)) = 2
        _CloudSpeed ("구름 흐르는 속도", Range(0, 0.05)) = 0.004
        _CloudDir ("구름 흐르는 방향 (xz)", Vector) = (1, 0, 0.3, 0)

        [Header(Nebula)]
        [HDR] _NebulaColor ("성운 색", Color) = (0.45, 0.12, 0.8, 1)
        [HDR] _NebulaColor2 ("성운 둘째 색", Color) = (0.1, 0.42, 0.6, 1)
        _NebulaStrength ("성운 세기", Range(0, 2)) = 0.6
        _NebulaAxis ("성운 띠 축 (띠가 이 방향에 수직인 큰 원을 따라 지난다)", Vector) = (-0.15, 0.15, 0.98, 0)
        _NebulaWidth ("성운 띠 폭", Range(0.05, 0.8)) = 0.26

        [Header(Aurora)]
        [HDR] _AuroraColor ("오로라 아래 색", Color) = (0.15, 0.75, 0.6, 1)
        [HDR] _AuroraColor2 ("오로라 위 색", Color) = (0.5, 0.15, 0.85, 1)
        _AuroraStrength ("오로라 세기", Range(0, 3)) = 0.9
        _AuroraAzimuth ("오로라 방위 (도, +X 에서 +Z 쪽으로)", Range(-180, 180)) = -150

        [Header(Shooting Stars)]
        _ShootingStarRate ("별똥별 빈도 (1분에 약 몇 개)", Range(0, 30)) = 6
        _ShootingStarBrightness ("별똥별 밝기", Range(0, 10)) = 3
    }

    SubShader
    {
        Tags { "Queue" = "Background" "RenderType" = "Background" "PreviewType" = "Skybox" "RenderPipeline" = "UniversalPipeline" }
        Cull Off
        ZWrite Off

        Pass
        {
            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _TopColor;
                half4 _HorizonColor;
                half4 _BottomColor;
                half _HorizonSharpness;
                half _StarDensity;
                half _StarBrightness;
                float4 _MoonDir;
                half4 _MoonColor;
                half _MoonSize;
                half _MoonGlow;
                half _MoonDetail;
                half4 _CloudColor;
                half4 _CloudLitColor;
                half _CloudCoverage;
                half _CloudOpacity;
                float _CloudScale;
                float _CloudSpeed;
                float4 _CloudDir;
                half4 _NebulaColor;
                half4 _NebulaColor2;
                half _NebulaStrength;
                float4 _NebulaAxis;
                half _NebulaWidth;
                half4 _AuroraColor;
                half4 _AuroraColor2;
                half _AuroraStrength;
                float _AuroraAzimuth;
                float _ShootingStarRate;
                half _ShootingStarBrightness;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 dir : TEXCOORD0;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS.xyz);
                o.dir = v.positionOS.xyz;
                return o;
            }

            // ───── 노이즈 (사인 없는 해시: GPU마다 결과가 같다) ─────
            float SkyHash13(float3 p3)
            {
                p3 = frac(p3 * 0.1031);
                p3 += dot(p3, p3.zyx + 31.32);
                return frac((p3.x + p3.y) * p3.z);
            }

            float SkyHash12(float2 p)
            {
                float3 p3 = frac(p.xyx * 0.1031);
                p3 += dot(p3, p3.yzx + 33.33);
                return frac((p3.x + p3.y) * p3.z);
            }

            float SkyNoise3(float3 x)
            {
                float3 i = floor(x);
                float3 f = frac(x);
                float3 u = f * f * (3.0 - 2.0 * f);
                float a = lerp(lerp(SkyHash13(i + float3(0, 0, 0)), SkyHash13(i + float3(1, 0, 0)), u.x),
                               lerp(SkyHash13(i + float3(0, 1, 0)), SkyHash13(i + float3(1, 1, 0)), u.x), u.y);
                float b = lerp(lerp(SkyHash13(i + float3(0, 0, 1)), SkyHash13(i + float3(1, 0, 1)), u.x),
                               lerp(SkyHash13(i + float3(0, 1, 1)), SkyHash13(i + float3(1, 1, 1)), u.x), u.y);
                return lerp(a, b, u.z);
            }

            float SkyNoise2(float2 x)
            {
                float2 i = floor(x);
                float2 f = frac(x);
                float2 u = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(SkyHash12(i), SkyHash12(i + float2(1, 0)), u.x),
                            lerp(SkyHash12(i + float2(0, 1)), SkyHash12(i + float2(1, 1)), u.x), u.y);
            }

            float SkyFbm3(float3 p, int octaves)
            {
                float s = 0.0, a = 0.5;
                for (int k = 0; k < octaves; k++)
                {
                    s += a * SkyNoise3(p);
                    p = p * 2.03 + 17.1;
                    a *= 0.5;
                }
                return s;
            }

            float SkyFbm2(float2 p, int octaves)
            {
                float s = 0.0, a = 0.5;
                for (int k = 0; k < octaves; k++)
                {
                    s += a * SkyNoise2(p);
                    p = float2(p.x * 1.6 - p.y * 1.2, p.x * 1.2 + p.y * 1.6) + 3.7;
                    a *= 0.5;
                }
                return s;
            }

            // 달 표면: 바다(어두운 얼룩) + 운석 구덩이 (가장자리가 밝은 둥근 패임)
            float MoonSurface(float2 local, float r)
            {
                float z = sqrt(saturate(1.0 - r * r));
                float maria = smoothstep(0.42, 0.68, SkyFbm2(local * 1.5 + 3.1, 4));
                float2 vp = local * 3.2;
                float2 vi = floor(vp);
                float f1 = 9.0;
                [unroll] for (int oy = -1; oy <= 1; oy++)
                {
                    [unroll] for (int ox = -1; ox <= 1; ox++)
                    {
                        float2 g = vi + float2(ox, oy);
                        float2 o = float2(SkyHash12(g), SkyHash12(g + 19.19));
                        float h = SkyHash12(g + 7.31);
                        float rad = 0.1 + 0.3 * h * h;
                        float v = SkyHash12(g + 3.77) > 0.45 ? length(g + o - vp) / rad : 9.0;
                        f1 = min(f1, v);
                    }
                }
                float crater = 1.0 - 0.22 * smoothstep(0.95, 0.4, f1) + 0.16 * smoothstep(0.75, 0.95, f1) * smoothstep(1.2, 0.95, f1);
                return (1.0 - _MoonDetail * 0.5 * maria) * lerp(1.0, crater, _MoonDetail) * (0.55 + 0.45 * z) * lerp(1.0, 0.62, _MoonDetail);
            }

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float3 d = normalize(i.dir);
                float h = d.y;
                float t = _Time.y;
                float above = saturate(h * 4.0);

                half3 color = lerp(_HorizonColor.rgb, _TopColor.rgb, pow(saturate(h), _HorizonSharpness));
                color = lerp(color, _BottomColor.rgb, saturate(-h * 5.0));

                float3 m = normalize(_MoonDir.xyz + float3(0, 0.0001, 0));
                float ang = acos(clamp(dot(d, m), -1.0, 1.0));

                // ───── 성운 띠 ─────
                float3 nb = normalize(_NebulaAxis.xyz + float3(0, 0.0001, 0));
                float bx = dot(d, nb) / max(_NebulaWidth, 0.01);
                float band = exp(-bx * bx);
                float n1 = SkyFbm3(d * 2.2 + float3(0, t * 0.003, 0), 4);
                float n2 = SkyFbm3(d * 4.6 + n1 * 1.8, 4);
                float neb = band * smoothstep(0.42, 0.9, n2 + band * 0.2) + band * 0.12;
                float dust = smoothstep(0.5, 0.78, SkyFbm3(d * 9.0 + 5.3, 3));
                neb *= 1.0 - 0.75 * dust * band;
                float hue = smoothstep(0.5, 0.75, SkyFbm3(d * 1.7 + 11.0, 3));
                color += lerp(_NebulaColor.rgb, _NebulaColor2.rgb, hue) * (neb * _NebulaStrength * saturate(h * 3.0 + 0.05));

                // ───── 별: 방향을 격자로 나눠 일부 칸에만 점을 찍는다 (성운 띠 안은 더 촘촘하게) ─────
                float3 p = d * 160.0;
                float3 cell = floor(p);
                float rnd = SkyHash13(cell);
                float density = _StarDensity * (1.0 + 2.5 * band);
                float star = step(1.0 - density, rnd) * smoothstep(0.32, 0.0, length(frac(p) - 0.5));
                float twinkle = 0.7 + 0.3 * sin(t * (1.0 + rnd * 3.0) + rnd * 40.0);
                color += star * twinkle * _StarBrightness * above;
                // 큰 별: 드물게, 푸르거나 보랏빛
                float3 p2 = d * 55.0;
                float3 c2 = floor(p2);
                float big = step(0.992, SkyHash13(c2 + 7.7)) * smoothstep(0.22, 0.0, length(frac(p2) - 0.5));
                half3 bigColor = lerp(half3(0.8, 0.75, 1.0), half3(0.6, 0.9, 1.0), SkyHash13(c2 + 1.3));
                color += bigColor * (big * _StarBrightness * 1.8 * above);

                // ───── 오로라: 지평선 위로 드리운 커튼 ─────
                if (_AuroraStrength > 0.001)
                {
                    // 방위를 오로라 중심 기준 (−π ~ π)으로 잰다: atan2 의 ±π 이음매가 오로라가 안 보이는 반대쪽에 오게
                    float az = atan2(d.z, d.x) - radians(_AuroraAzimuth);
                    az -= 6.2831853 * floor((az + 3.14159265) / 6.2831853);
                    float side = smoothstep(0.55, 1.0, cos(az) * 0.5 + 0.5);
                    float baseH = 0.08 + 0.05 * sin(az * 3.0 + t * 0.07) + 0.03 * sin(az * 7.3 - t * 0.11);
                    float hh = h - baseH;
                    float hp = max(hh, 0.0);
                    float curtain = smoothstep(0.0, 0.015, hh) * exp(-hp * 8.0) * (0.55 + 0.45 * exp(-hp * 40.0));
                    float rays = smoothstep(0.35, 0.8, SkyFbm2(float2(az * 26.0 + t * 0.05, hh * 0.8), 4));
                    half3 auroraColor = lerp(_AuroraColor.rgb, _AuroraColor2.rgb, saturate(hh * 5.0));
                    color += auroraColor * (curtain * rays * side * _AuroraStrength);
                }

                // ───── 구름: 하늘을 평면에 투영해 바람 방향으로 늘린 얇은 띠 ─────
                float cloud = 0.0;
                if (_CloudCoverage > 0.001)
                {
                    float ch = max(h, 0.0) + 0.1;
                    float2 cuv = d.xz / ch;
                    float2 cd = normalize(_CloudDir.xz + float2(0.0001, 0));
                    float along = dot(cuv, cd);
                    float across = -cuv.x * cd.y + cuv.y * cd.x;
                    float2 q = float2(along * 0.35, across * 1.6) * _CloudScale + float2(t * _CloudSpeed * 60.0, 0);
                    float cn = SkyFbm2(q, 5);
                    cloud = smoothstep(1.0 - _CloudCoverage - 0.05, 1.0 - _CloudCoverage + 0.3, cn);
                    cloud *= smoothstep(0.02, 0.12, h) * (1.0 - smoothstep(0.3, 0.75, h));
                    float lit = exp(-ang * 2.2) * (0.35 + 0.65 * (1.0 - cloud));
                    half3 cloudColor = lerp(_CloudColor.rgb, _CloudLitColor.rgb, saturate(lit));
                    cloudColor = lerp(cloudColor, _HorizonColor.rgb, exp(-max(h, 0.0) * 8.0) * 0.6);
                    color = lerp(color, cloudColor, cloud * _CloudOpacity);
                }

                // ───── 달과 달무리 (구름에 가려진다) ─────
                float disc = smoothstep(_MoonSize, _MoonSize * 0.9, ang);
                float moonTex = 1.0;
                if (disc > 0.0)
                {
                    float3 refAxis = abs(m.y) > 0.99 ? float3(1, 0, 0) : float3(0, 1, 0);
                    float3 t1 = normalize(cross(m, refAxis));
                    float3 t2 = cross(t1, m);
                    float2 local = float2(dot(d, t1), dot(d, t2)) / sin(_MoonSize);
                    moonTex = MoonSurface(local, length(local));
                }
                float glow = exp(-ang * 7.0) * _MoonGlow;
                color += _MoonColor.rgb * (disc * moonTex * (1.0 - cloud * 0.85) + glow * 0.22 * (1.0 - cloud * 0.5));

                // ───── 별똥별: 시간 칸마다 무작위 자리에서 짧게 긋는다 (두 줄기) ─────
                if (_ShootingStarRate > 0.001)
                {
                    float2 uv = d.xz / (1.0 + max(d.y, 0.0));     // 하늘을 위에서 내려다본 원판 (꼭대기 = 0, 지평선 = 1)
                    [unroll] for (int slot = 0; slot < 2; slot++)
                    {
                        float period = 60.0 / _ShootingStarRate * (1.0 + slot * 0.61) * 2.0;
                        float tt = t + slot * 17.3;
                        float k = floor(tt / period);
                        float lt = tt - k * period;
                        const float duration = 0.9;
                        if (lt < duration)
                        {
                            float hk = SkyHash12(float2(k, slot * 7.0));
                            float hk2 = SkyHash12(float2(k + 3.1, slot * 5.0 + 1.0));
                            float hk3 = SkyHash12(float2(k + 9.7, slot * 3.0 + 2.0));
                            float a0 = hk * 6.2831853;
                            float2 start = float2(cos(a0), sin(a0)) * (0.25 + 0.45 * hk2);
                            float a1 = a0 + (hk3 - 0.5) * 1.6;
                            float2 dirv = float2(cos(a1), sin(a1));
                            float prog = lt / duration;
                            float2 head = start + dirv * (0.3 * prog);
                            float tail = 0.12 * min(1.0, prog * 3.0);
                            float s = saturate(-dot(uv - head, dirv) / max(tail, 0.0001));
                            float dist = length(uv - (head - dirv * (s * tail)));
                            float w = dist / 0.0022;
                            float inten = exp(-w * w) * pow(1.0 - s, 1.5) * sin(3.14159265 * prog) * above;
                            color += half3(0.85, 0.8, 1.0) * (inten * _ShootingStarBrightness);
                        }
                    }
                }

                return half4(color, 1);
            }
            ENDHLSL
        }
    }
}
