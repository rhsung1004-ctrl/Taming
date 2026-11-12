using UnityEngine;

namespace Necro.Proto
{
    // 잠깐 보였다 사라지는 효과 (폭발, 범위 예고)
    public class Fx : MonoBehaviour
    {
        float life, t, from, to;
        bool flat;

        public static void Burst(Vector3 pos, float radius, Color color, float life = 0.35f)
        {
            var tr = Util.Part(PrimitiveType.Sphere, null, pos, Vector3.one * 0.2f, color, default(Vector3), true);
            var f = tr.gameObject.AddComponent<Fx>();
            f.life = life;
            f.from = 0.3f;
            f.to = radius * 2f;
        }

        // 바닥에 깔리는 원 (범위 공격 예고)
        public static void Ring(Vector3 pos, float radius, Color color, float life)
        {
            var tr = Util.Part(PrimitiveType.Cylinder, null, pos + Vector3.up * 0.08f, new Vector3(0.2f, 0.02f, 0.2f), color, default(Vector3), true);
            var f = tr.gameObject.AddComponent<Fx>();
            f.life = life;
            f.from = radius * 0.3f;
            f.to = radius * 2f;
            f.flat = true;
        }

        void Update()
        {
            t += Time.deltaTime;
            float k = Mathf.Clamp01(t / life);
            float s = Mathf.Lerp(from, to, flat ? k : 1f - (1f - k) * (1f - k));
            transform.localScale = flat ? new Vector3(s, 0.02f, s) : Vector3.one * s;
            if (t >= life) Destroy(gameObject);
        }
    }
}
