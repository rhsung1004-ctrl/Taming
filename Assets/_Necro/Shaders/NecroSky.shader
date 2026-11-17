// 다크 판타지 밤하늘 (스카이박스): 위에서 지평선으로 번지는 색, 별, 달과 달무리.
// 지평선 색(_HorizonColor)은 안개 색과 같게 맞춰야 먼 땅이 하늘에 자연스럽게 녹아든다.
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
    }

    SubShader
    {
        Tags { "Queue" = "Background" "RenderType" = "Background" "PreviewType" = "Skybox" "RenderPipeline" = "UniversalPipeline" }
        Cull Off
        ZWrite Off

        Pass
        {
            HLSLPROGRAM
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

            float Hash(float3 p)
            {
                p = frac(p * 0.3183099 + 0.1);
                p *= 17.0;
                return frac(p.x * p.y * p.z * (p.x + p.y + p.z));
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 d = normalize(i.dir);
                float h = d.y;

                half3 color = lerp(_HorizonColor.rgb, _TopColor.rgb, pow(saturate(h), _HorizonSharpness));
                color = lerp(color, _BottomColor.rgb, saturate(-h * 5.0));

                // 별: 방향을 격자로 나눠 일부 칸에만 점을 찍는다
                float3 p = d * 160.0;
                float3 cell = floor(p);
                float rnd = Hash(cell);
                float star = step(1.0 - _StarDensity, rnd) * smoothstep(0.32, 0.0, length(frac(p) - 0.5));
                float twinkle = 0.7 + 0.3 * sin(_Time.y * (1.0 + rnd * 3.0) + rnd * 40.0);
                color += star * twinkle * _StarBrightness * saturate(h * 4.0);

                // 달과 달무리
                float3 m = normalize(_MoonDir.xyz + float3(0, 0.0001, 0));
                float ang = acos(clamp(dot(d, m), -1.0, 1.0));
                float disc = smoothstep(_MoonSize, _MoonSize * 0.9, ang);
                float glow = exp(-ang * 7.0) * _MoonGlow;
                color += _MoonColor.rgb * (disc + glow * 0.22);

                return half4(color, 1);
            }
            ENDHLSL
        }
    }
}
