// 사령술사 3D 캐릭터용 애니풍 툰 셰이더 (URP).
//  - 2단 음영: 밝은 면 / 그늘 면이 또렷하게 나뉜다. 그늘은 검게 죽지 않고 _ShadeColor(보랏빛)로 물든다
//  - 외곽선: 뒤집은 면을 살짝 부풀려 그린다 (Outline 패스)
//  - 가장자리 빛(림), 또렷한 하이라이트, 발광
//  - 영혼 효과(_Soul): 지배한 망자는 같은 모델에 보랏빛 영혼 불꽃이 가장자리에서 일렁인다
// 그림자 받기·드리우기, 안개, 추가 광원(등불), GPU 인스턴싱, SRP Batcher 지원.
Shader "Necro/Toon"
{
    Properties
    {
        [Header(Base)]
        [MainTexture] _BaseMap ("기본 텍스처", 2D) = "white" {}
        [MainColor] _BaseColor ("기본 색", Color) = (1, 1, 1, 1)

        [Header(Shade)]
        _ShadeColor ("그늘 색 (곱해짐)", Color) = (0.52, 0.46, 0.72, 1)
        _ShadeThreshold ("그늘 경계 위치", Range(0, 1)) = 0.5
        _ShadeSmooth ("그늘 경계 부드러움", Range(0.001, 0.5)) = 0.03
        _AmbientStrength ("주변광 세기", Range(0, 2)) = 1

        [Header(Highlight and Rim)]
        _SpecStrength ("하이라이트 세기", Range(0, 2)) = 0
        _SpecSize ("하이라이트 크기", Range(0.001, 0.5)) = 0.08
        [HDR] _RimColor ("가장자리 빛 색", Color) = (0.55, 0.6, 1, 1)
        _RimPower ("가장자리 빛 폭", Range(0.5, 8)) = 3
        _RimStrength ("가장자리 빛 세기", Range(0, 2)) = 0.35
        [HDR] _EmissionColor ("발광 색", Color) = (0, 0, 0, 1)

        [Header(Outline)]
        _OutlineColor ("외곽선 색", Color) = (0.05, 0.03, 0.09, 1)
        _OutlineWidth ("외곽선 굵기", Range(0, 6)) = 1.6

        [Header(Soul)]
        _Soul ("영혼 효과 (0 적, 1 지배된 망자)", Range(0, 1)) = 0
        [HDR] _SoulColor ("영혼 색", Color) = (1.7, 0.9, 3.2, 1)
        _SoulTint ("영혼 물듦 (몸 색을 보랏빛으로)", Range(0, 1)) = 0.45
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        TEXTURE2D(_BaseMap);
        SAMPLER(sampler_BaseMap);

        // 모든 패스가 같은 버퍼를 써야 SRP Batcher가 묶어 그린다
        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            half4 _ShadeColor;
            half _ShadeThreshold;
            half _ShadeSmooth;
            half _AmbientStrength;
            half _SpecStrength;
            half _SpecSize;
            half4 _RimColor;
            half _RimPower;
            half _RimStrength;
            half4 _EmissionColor;
            half4 _OutlineColor;
            half _OutlineWidth;
            half _Soul;
            half4 _SoulColor;
            half _SoulTint;
        CBUFFER_END
        ENDHLSL

        // ───────────── 본체 ─────────────
        Pass
        {
            Name "ToonForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile _ _FORWARD_PLUS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                float3 normalWS : TEXCOORD2;
                half fogFactor : TEXCOORD3;
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
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.uv = TRANSFORM_TEX(v.uv, _BaseMap);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);

                half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv) * _BaseColor;
                half3 albedo = tex.rgb;
                // 지배된 망자: 몸 색이 보랏빛으로 물든다
                half3 soulHue = normalize(_SoulColor.rgb + 0.0001) * 1.25;
                half lum = dot(albedo, half3(0.3, 0.59, 0.11));
                albedo = lerp(albedo, lerp(albedo, lum * soulHue, 0.75), _Soul * _SoulTint);

                float3 N = normalize(i.normalWS);
                float3 V = GetWorldSpaceNormalizeViewDir(i.positionWS);

                Light mainLight = GetMainLight(TransformWorldToShadowCoord(i.positionWS));
                half ndl = dot(N, mainLight.direction) * 0.5 + 0.5;
                half lit = smoothstep(_ShadeThreshold - _ShadeSmooth, _ShadeThreshold + _ShadeSmooth, ndl);
                // 드리운 그림자도 같은 2단 음영으로
                lit = min(lit, smoothstep(0.35, 0.65, mainLight.shadowAttenuation));

                half3 ambient = SampleSH(N) * _AmbientStrength;
                half3 color = albedo * (mainLight.color * lerp(_ShadeColor.rgb, half3(1, 1, 1), lit) + ambient);

                // 등불 같은 추가 광원: 닿는 면만 또렷하게 밝힌다
                #if defined(_ADDITIONAL_LIGHTS)
                {
                    uint lightCount = GetAdditionalLightsCount();
                    InputData inputData = (InputData)0;
                    inputData.positionWS = i.positionWS;
                    inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
                    LIGHT_LOOP_BEGIN(lightCount)
                        Light l = GetAdditionalLight(lightIndex, i.positionWS, half4(1, 1, 1, 1));
                        half a = smoothstep(0.42, 0.58, dot(N, l.direction) * 0.5 + 0.5);
                        color += albedo * l.color * (l.distanceAttenuation * l.shadowAttenuation * a);
                    LIGHT_LOOP_END
                }
                #endif

                // 또렷한 하이라이트
                float3 H = normalize(mainLight.direction + V);
                half spec = smoothstep(1.0 - _SpecSize - 0.01, 1.0 - _SpecSize + 0.01, dot(N, H));
                color += mainLight.color * (spec * _SpecStrength * lit);

                // 가장자리 빛
                half fres = 1.0 - saturate(dot(N, V));
                half rim = smoothstep(0.45, 0.6, pow(fres, _RimPower));
                color += _RimColor.rgb * (rim * _RimStrength * (0.35 + 0.65 * lit));

                // 영혼 불꽃: 가장자리에서 위로 일렁인다
                half flicker = 0.75 + 0.25 * sin(_Time.y * 2.6 + i.positionWS.y * 5.0 + i.positionWS.x * 1.7);
                color += _SoulColor.rgb * (pow(fres, 2.2) * flicker * _Soul);

                color += _EmissionColor.rgb;
                color = MixFog(color, i.fogFactor);
                return half4(color, 1);
            }
            ENDHLSL
        }

        // ───────────── 외곽선 ─────────────
        Pass
        {
            Name "Outline"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Cull Front

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                half fogFactor : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 positionWS = TransformObjectToWorld(v.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(v.normalOS);
                // 멀어져도 화면에서 비슷한 굵기로 보이게 (너무 가깝거나 멀 때는 제한)
                float dist = distance(_WorldSpaceCameraPos, positionWS);
                positionWS += normalWS * (_OutlineWidth * 0.0012 * clamp(dist, 1.5, 14.0));
                o.positionCS = TransformWorldToHClip(positionWS);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                half3 color = lerp(_OutlineColor.rgb, _SoulColor.rgb * 0.22, _Soul);
                color = MixFog(color, i.fogFactor);
                return half4(color, 1);
            }
            ENDHLSL
        }

        // ───────────── 그림자 드리우기 ─────────────
        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(v);
                float3 positionWS = TransformObjectToWorld(v.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(v.normalOS);
                #if defined(_CASTING_PUNCTUAL_LIGHT_SHADOW)
                    float3 lightDirectionWS = normalize(_LightPosition - positionWS);
                #else
                    float3 lightDirectionWS = _LightDirection;
                #endif
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS));
                #if UNITY_REVERSED_Z
                    positionCS.z = min(positionCS.z, UNITY_NEAR_CLIP_VALUE);
                #else
                    positionCS.z = max(positionCS.z, UNITY_NEAR_CLIP_VALUE);
                #endif
                o.positionCS = positionCS;
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                return 0;
            }
            ENDHLSL
        }

        // ───────────── 깊이 (후처리·앰비언트 오클루전용) ─────────────
        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS.xyz);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                return 0;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 normalWS : TEXCOORD0;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS.xyz);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                return half4(normalize(i.normalWS), 0);
            }
            ENDHLSL
        }
    }

    FallBack "Hidden/Universal Render Pipeline/FallbackError"
}
