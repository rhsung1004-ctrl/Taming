// 풀·덩굴·이끼·거미줄용 잎 셰이더 (URP 6000.0).
//  - 색 = 잎 아틀라스(foliage_atlas) × 정점 색 × _BaseColor. 알파 컷, 양면 (뒷면은 법선을 뒤집는다)
//  - 바람: 전역 _NecroWind(방향·세기), _NecroWindParams(빈도·돌풍·물결 크기·잔떨림). 정점 알파(0 뿌리 ~ 1 끝)만큼 흔들린다
//  - 상호작용: 전역 _NecroInteractPos(xyz 주인공 발 위치, w 반지름) 주변의 풀이 밀려난다
//  - 애니풍 조명: 감싸는 빛 + 그늘은 보랏빛(_ShadeColor), 빛을 등진 잎은 반투과로 비친다
//  - 멀리서는 정점 법선 대신 위쪽 법선을 섞어 풀밭이 한 덩어리로 부드럽게 보인다
//  - 거리 축소(_FadeStart ~ _FadeEnd): 포기를 뿌리 쪽으로 오그라뜨려 지형 풀이 끊기는 경계를 감춘다. 기본은 꺼짐 (지형 풀 전용 재질에서 켠다)
// 주광 그림자 받기·드리우기(알파 컷 + 같은 바람), 추가 광원(Forward+ 포함), 안개, LOD 디더 전환,
// GPU 인스턴싱(지형 풀), SRP Batcher(모든 패스가 같은 UnityPerMaterial).
// 전역 값은 NecroWind 컴포넌트가 매 프레임 넣는다. 없으면 바람·상호작용이 꺼진 상태로 그려진다.
Shader "Necro/Foliage"
{
    Properties
    {
        [Header(Base)]
        [MainTexture] _BaseMap ("잎 아틀라스", 2D) = "white" {}
        [MainColor] _BaseColor ("색 (곱해짐)", Color) = (1, 1, 1, 1)
        _Cutoff ("알파 컷", Range(0.05, 0.95)) = 0.5
        [ToggleUI] _VertexColorSRGB ("정점 색이 sRGB (Blender 내보내기 그대로)", Float) = 1

        [Header(Shade)]
        _ShadeColor ("그늘 색 (곱해짐, 보랏빛)", Color) = (0.5, 0.42, 0.74, 1)
        _ShadeThreshold ("그늘 경계 위치", Range(0, 1)) = 0.42
        _ShadeSmooth ("그늘 경계 부드러움", Range(0.01, 0.6)) = 0.28
        _Wrap ("감싸는 빛 (클수록 뒤까지 밝음)", Range(0, 1)) = 0.5
        _AmbientStrength ("주변광 세기", Range(0, 2)) = 1
        _RootDarken ("뿌리 쪽 어둡게 (작을수록 어두움)", Range(0, 1)) = 0.45

        [Header(Translucency)]
        _TransColor ("반투과 색", Color) = (0.62, 0.5, 0.95, 1)
        _TransStrength ("반투과 세기", Range(0, 3)) = 0.9
        _TransPower ("반투과 모임 (클수록 좁게)", Range(1, 16)) = 4

        [Header(Rim)]
        [HDR] _RimColor ("잎 끝 은빛", Color) = (0.6, 0.66, 1, 1)
        _RimStrength ("잎 끝 은빛 세기", Range(0, 2)) = 0.3

        [Header(Far Normal)]
        _UpNormalNear ("가까이서 위쪽 법선 비율", Range(0, 1)) = 0.3
        _UpNormalStart ("위쪽 법선 섞기 시작 거리 (m)", Float) = 8
        _UpNormalEnd ("위쪽 법선만 쓰는 거리 (m)", Float) = 45

        [Header(Wind)]
        _WindStrength ("바람 세기 배율", Range(0, 3)) = 1
        _InteractStrength ("밀려나는 세기", Range(0, 2)) = 1

        // 지형 풀 전용 재질에서만 켠다. Foliage.mat 은 폐허·절벽·고목의 덩굴·이끼도 같이 쓰므로 0 (끔) 으로 둔다
        [Header(Distance Fade)]
        _FadeStart ("오그라들기 시작 거리 (m)", Float) = 0
        _FadeEnd ("다 오그라드는 거리 (m, 0 = 끔)", Float) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        TEXTURE2D(_BaseMap);
        SAMPLER(sampler_BaseMap);

        // 모든 패스가 같은 버퍼를 써야 SRP Batcher가 묶어 그린다
        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            half _Cutoff;
            half _VertexColorSRGB;
            half4 _ShadeColor;
            half _ShadeThreshold;
            half _ShadeSmooth;
            half _Wrap;
            half _AmbientStrength;
            half _RootDarken;
            half4 _TransColor;
            half _TransStrength;
            half _TransPower;
            half4 _RimColor;
            half _RimStrength;
            half _UpNormalNear;
            float _UpNormalStart;
            float _UpNormalEnd;
            half _WindStrength;
            half _InteractStrength;
            float _FadeStart;
            float _FadeEnd;
        CBUFFER_END

        // 전역 (NecroWind 가 넣는다)
        float4 _NecroWind;          // xyz: 바람 방향 (수평, 정규화), w: 세기 (잎 끝이 밀리는 거리 m)
        float4 _NecroWindParams;    // x: 흔들림 빈도 (Hz), y: 돌풍 세기, z: 돌풍 물결 크기 (1/m), w: 잔떨림
        float4 _NecroInteractPos;   // xyz: 주인공 발 위치, w: 반지름 (0 이면 꺼짐)

        // 보이는 거리 끝에서 포기를 뿌리 쪽으로 오그라뜨리는 비율 (0 그대로 ~ 1 점).
        // 지형 풀은 지형이 정한 거리(detailObjectDistance)에서 그냥 끊기므로, 그 조금 앞에서 다 오그라들게 해 경계가 안 보이게 한다.
        // 디더 대신 크기를 줄이므로 과대 그리기가 없고, 다 오그라든 포기는 삼각형이 점이 되어 그려지지 않는다
        float NecroFoliageFadeT(float3 originWS)
        {
            if (_FadeEnd <= 0.0) return 0.0;              // 끔 (재질 값이라 모든 정점이 같은 쪽으로 간다)
            float dist = distance(GetCameraPositionWS(), originWS);
            return saturate((dist - _FadeStart) / max(_FadeEnd - _FadeStart, 0.01));
        }

        // 바람 + 상호작용 + 거리 축소로 움직인 월드 위치. sway: 정점 알파 (0 뿌리 ~ 1 끝)
        // 본체·그림자·깊이·깊이+법선 패스가 모두 이 함수를 써서 같은 자리에 그려진다
        float3 NecroFoliageDeform(float3 positionWS, float3 originWS, half sway)
        {
            float fadeT = NecroFoliageFadeT(originWS);
            [branch] if (fadeT >= 1.0) return originWS;   // 다 오그라든 포기: 바람 계산을 건너뛴다

            float amount = sway * (0.45 + 0.55 * sway);      // 끝으로 갈수록 휘는 곡선
            float3 dir = _NecroWind.xyz;
            float strength = _NecroWind.w * _WindStrength;
            float freq = max(_NecroWindParams.x, 0.01);
            float t = _Time.y;

            // 큰 돌풍 물결: 바람 방향으로 풀밭을 쓸고 지나간다
            float along = dot(originWS.xz, dir.xz) * _NecroWindParams.z;
            float gust = sin((along - t * freq * 0.23) * 6.2831853) * 0.5 + 0.5;
            gust = gust * gust * _NecroWindParams.y;
            // 포기마다 다른 흔들림
            float phase = dot(originWS.xz, float2(0.731, 1.379));
            float wave = sin(t * freq * 6.2831853 + phase) * 0.65 + sin(t * freq * 14.51 + phase * 2.3) * 0.35;
            float bend = strength * amount * (0.3 + gust + wave * (0.25 + gust * 0.5));
            float3 offset = dir * bend;
            // 잔떨림: 잎 하나하나가 바람에 떤다
            float flutter = sin(t * freq * 41.0 + dot(positionWS, float3(3.1, 2.3, 2.7))) * _NecroWindParams.w * strength * sway;
            offset += float3(-dir.z, 0.35, dir.x) * flutter;

            // 주인공 주변의 풀이 밀려난다
            if (_NecroInteractPos.w > 0.001)
            {
                float2 d2 = positionWS.xz - _NecroInteractPos.xz;
                float dist = length(d2);
                // 반지름 밖은 fall = 0 이라 결과가 같다. 화면의 풀 정점 거의 전부가 여기서 나간다
                [branch] if (dist < _NecroInteractPos.w)
                {
                    float fall = saturate(1.0 - dist / _NecroInteractPos.w);
                    fall = fall * fall * (3.0 - 2.0 * fall);
                    fall *= saturate(2.0 - abs(positionWS.y - _NecroInteractPos.y));   // 높이 차가 크면 (절벽 위 등) 무시
                    float push = fall * amount * _InteractStrength;
                    offset.xz += (d2 / max(dist, 0.001)) * (push * _NecroInteractPos.w * 0.55);
                    offset.y -= push * 0.3;
                }
            }

            // 옆으로 밀린 만큼 조금 낮춰 길이가 늘어나 보이지 않게
            offset.y -= dot(offset.xz, offset.xz) * 0.35 * sway;
            return lerp(positionWS + offset, originWS, fadeT);
        }

        // Blender 는 정점 색을 sRGB 로 내보낸다 (colors_type='SRGB'). 선형 색으로 바꿔 쓴다
        half3 NecroVertexColor(half3 c)
        {
            half3 lo = c / 12.92;
            half3 hi = pow(abs((c + 0.055) / 1.055), 2.4);
            half3 lin = lerp(hi, lo, step(c, 0.04045));      // c <= 0.04045 이면 lo (벡터 삼항 연산 없이)
            return lerp(c, lin, _VertexColorSRGB);
        }

        // 멀리서는 위쪽 법선을 섞는다 (풀밭이 부드럽게)
        float3 NecroFoliageNormal(float3 normalWS, float3 positionWS)
        {
            float dist = distance(GetCameraPositionWS(), positionWS);
            float farT = saturate((dist - _UpNormalStart) / max(_UpNormalEnd - _UpNormalStart, 0.01));
            return normalize(lerp(normalWS, float3(0, 1, 0), lerp(_UpNormalNear, 1.0, farT)));
        }

        half NecroFoliageAlpha(float2 uv)
        {
            return SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv).a * _BaseColor.a;
        }
        ENDHLSL

        // ───────────── 본체 ─────────────
        Pass
        {
            Name "FoliageForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile _ _FORWARD_PLUS
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                half4 color : COLOR;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                float3 normalWS : TEXCOORD2;
                half4 color : TEXCOORD3;          // rgb: 선형 색, a: 흔들림(높이)
                half fogFactor : TEXCOORD4;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 originWS = TransformObjectToWorld(float3(0, 0, 0));
                float3 positionWS = NecroFoliageDeform(TransformObjectToWorld(v.positionOS.xyz), originWS, v.color.a);
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.uv = TRANSFORM_TEX(v.uv, _BaseMap);
                o.color = half4(NecroVertexColor(v.color.rgb), v.color.a);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            // 감싸는 빛 + 반투과 (주광·추가 광원 공통)
            half3 FoliageLight(half3 albedo, float3 N, float3 V, half3 lightDir, half3 lightColor, half atten, half sway, half shadeAll)
            {
                half ndl = dot(N, lightDir);
                half wrap = saturate((ndl + _Wrap) / (1.0 + _Wrap));
                half lit = smoothstep(_ShadeThreshold - _ShadeSmooth, _ShadeThreshold + _ShadeSmooth, wrap) * atten;
                half3 c = albedo * lightColor * lerp(_ShadeColor.rgb * shadeAll, half3(1, 1, 1), lit);
                // 빛을 등진 잎: 달빛이 잎을 뚫고 비친다
                half back = pow(saturate(dot(V, -lightDir)), _TransPower);
                c += albedo * _TransColor.rgb * lightColor * (back * _TransStrength * atten * (0.35 + 0.65 * sway));
                return c;
            }

            half4 frag(Varyings i, FRONT_FACE_TYPE face : FRONT_FACE_SEMANTIC) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);

                half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv);
                clip(tex.a * _BaseColor.a - _Cutoff);
                #if defined(LOD_FADE_CROSSFADE)
                    LODFadeCrossFade(i.positionCS);
                #endif

                half3 albedo = tex.rgb * i.color.rgb * _BaseColor.rgb;
                half sway = i.color.a;
                float3 N = normalize(i.normalWS) * IS_FRONT_VFACE(face, 1.0, -1.0);
                N = NecroFoliageNormal(N, i.positionWS);
                float3 V = GetWorldSpaceNormalizeViewDir(i.positionWS);
                half rootAO = lerp(_RootDarken, 1.0, saturate(sway * 1.6));

                // 주광 (달빛): 그림자는 거리 페이드까지 포함된 MainLightShadow 사용
                float4 shadowCoord = TransformWorldToShadowCoord(i.positionWS);
                Light mainLight = GetMainLight(shadowCoord, i.positionWS, half4(1, 1, 1, 1));
                half mainAtten = mainLight.shadowAttenuation * mainLight.distanceAttenuation;
                half3 color = FoliageLight(albedo, N, V, mainLight.direction, mainLight.color, mainAtten, sway, mainLight.distanceAttenuation);
                color += albedo * SampleSH(N) * _AmbientStrength;

                // 잎 끝 은빛 (애니풍 가장자리 빛)
                half fres = pow(1.0 - saturate(abs(dot(N, V))), 3.0);
                color += _RimColor.rgb * mainLight.color * (fres * _RimStrength * sway * mainAtten);

                #if defined(_ADDITIONAL_LIGHTS)
                {
                    InputData inputData = (InputData)0;
                    inputData.positionWS = i.positionWS;
                    inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
                    uint lightCount = GetAdditionalLightsCount();
                    #if USE_FORWARD_PLUS
                    [loop] for (uint li = 0; li < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); li++)
                    {
                        Light dl = GetAdditionalLight(li, i.positionWS, half4(1, 1, 1, 1));
                        color += FoliageLight(albedo, N, V, dl.direction, dl.color, dl.distanceAttenuation * dl.shadowAttenuation, sway, 0.0);
                    }
                    #endif
                    LIGHT_LOOP_BEGIN(lightCount)
                        Light l = GetAdditionalLight(lightIndex, i.positionWS, half4(1, 1, 1, 1));
                        // 추가 광원은 그늘 색을 더하지 않는다 (등불이 닿는 곳만 밝힌다)
                        color += FoliageLight(albedo, N, V, l.direction, l.color, l.distanceAttenuation * l.shadowAttenuation, sway, 0.0);
                    LIGHT_LOOP_END
                }
                #endif

                color *= rootAO;
                // 안개 값을 half 에 먼저 담는다: InitializeInputDataFog 는 PC 에서 float 을 돌려주므로 MixFog(half3, float) 이면
                // half·float 두 오버로드 사이에서 모호한 호출이 될 수 있다 (URP 자신도 half 변수에 담아 부른다)
                half fogCoord = (half)InitializeInputDataFog(float4(i.positionWS, 1.0), i.fogFactor);
                color = MixFog(color, fogCoord);
                return half4(color, 1);
            }
            ENDHLSL
        }

        // ───────────── 그림자 드리우기 (알파 컷 + 같은 바람) ─────────────
        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"
            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                half4 color : COLOR;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                float3 originWS = TransformObjectToWorld(float3(0, 0, 0));
                float3 positionWS = NecroFoliageDeform(TransformObjectToWorld(v.positionOS.xyz), originWS, v.color.a);
                float3 normalWS = TransformObjectToWorldNormal(v.normalOS);
                #if defined(_CASTING_PUNCTUAL_LIGHT_SHADOW)
                    float3 lightDirectionWS = normalize(_LightPosition - positionWS);
                #else
                    float3 lightDirectionWS = _LightDirection;
                #endif
                o.positionCS = ApplyShadowClamping(TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS)));
                o.uv = TRANSFORM_TEX(v.uv, _BaseMap);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                clip(NecroFoliageAlpha(i.uv) - _Cutoff);
                #if defined(LOD_FADE_CROSSFADE)
                    LODFadeCrossFade(i.positionCS);
                #endif
                return 0;
            }
            ENDHLSL
        }

        // ───────────── 깊이 (후처리·깊이 텍스처용) ─────────────
        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_instancing

            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            struct Attributes
            {
                float4 positionOS : POSITION;
                half4 color : COLOR;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 originWS = TransformObjectToWorld(float3(0, 0, 0));
                float3 positionWS = NecroFoliageDeform(TransformObjectToWorld(v.positionOS.xyz), originWS, v.color.a);
                o.positionCS = TransformWorldToHClip(positionWS);
                o.uv = TRANSFORM_TEX(v.uv, _BaseMap);
                return o;
            }

            half frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                clip(NecroFoliageAlpha(i.uv) - _Cutoff);
                #if defined(LOD_FADE_CROSSFADE)
                    LODFadeCrossFade(i.positionCS);
                #endif
                return i.positionCS.z;
            }
            ENDHLSL
        }

        // ───────────── 깊이 + 법선 (SSAO 등) ─────────────
        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_fragment _ _GBUFFER_NORMALS_OCT
            #pragma multi_compile_instancing

            #if defined(LOD_FADE_CROSSFADE)
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
            #endif

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                half4 color : COLOR;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionWS : TEXCOORD2;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 originWS = TransformObjectToWorld(float3(0, 0, 0));
                float3 positionWS = NecroFoliageDeform(TransformObjectToWorld(v.positionOS.xyz), originWS, v.color.a);
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.uv = TRANSFORM_TEX(v.uv, _BaseMap);
                return o;
            }

            half4 frag(Varyings i, FRONT_FACE_TYPE face : FRONT_FACE_SEMANTIC) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                clip(NecroFoliageAlpha(i.uv) - _Cutoff);
                #if defined(LOD_FADE_CROSSFADE)
                    LODFadeCrossFade(i.positionCS);
                #endif
                float3 N = normalize(i.normalWS) * IS_FRONT_VFACE(face, 1.0, -1.0);
                N = NecroFoliageNormal(N, i.positionWS);
                #if defined(_GBUFFER_NORMALS_OCT)
                    float2 octNormalWS = PackNormalOctQuadEncode(N);
                    float2 remappedOctNormalWS = saturate(octNormalWS * 0.5 + 0.5);
                    return half4(PackFloat2To888(remappedOctNormalWS), 0.0);
                #else
                    return half4(N, 0.0);
                #endif
            }
            ENDHLSL
        }
    }

    FallBack "Hidden/Universal Render Pipeline/FallbackError"
}
