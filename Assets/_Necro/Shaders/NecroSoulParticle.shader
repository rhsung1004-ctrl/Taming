// 떠도는 영혼 불티·땅안개용 가산(Additive) 입자. 텍스처 없이 부드러운 원을 그린다.
Shader "Necro/SoulParticle"
{
    Properties
    {
        [HDR] _TintColor ("색", Color) = (1.2, 0.7, 2.2, 1)
        _Softness ("가장자리 부드러움 (클수록 흐릿)", Range(0.5, 4)) = 2
    }

    SubShader
    {
        Tags { "Queue" = "Transparent" "RenderType" = "Transparent" "IgnoreProjector" = "True" "RenderPipeline" = "UniversalPipeline" }
        Blend SrcAlpha One
        ZWrite Off
        Cull Off

        Pass
        {
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _TintColor;
                half _Softness;
            CBUFFER_END

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
                half4 color : COLOR;
                float2 uv : TEXCOORD0;
                half fogFactor : TEXCOORD1;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS.xyz);
                o.color = v.color * _TintColor;
                o.uv = v.uv;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                half r = saturate(1.0 - length(i.uv - 0.5) * 2.0);
                half a = pow(r, _Softness);
                half3 color = MixFogColor(i.color.rgb, half3(0, 0, 0), i.fogFactor);   // 멀리서는 안개에 묻힌다
                return half4(color, a * i.color.a);
            }
            ENDHLSL
        }
    }
}
