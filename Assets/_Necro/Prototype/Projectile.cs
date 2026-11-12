using UnityEngine;

namespace Necro.Proto
{
    public class Projectile : MonoBehaviour
    {
        Combatant src, dst;
        Vector3 point;
        bool toPoint;
        Team hits;
        float power, speed, aoe, life = 4f;
        Color color;

        static Projectile Make(Vector3 from, float size, Color color)
        {
            var tr = Util.Part(PrimitiveType.Sphere, null, from, Vector3.one * size, color, default(Vector3), true);
            var p = tr.gameObject.AddComponent<Projectile>();
            p.color = color;
            return p;
        }

        // 대상을 따라가는 탄
        public static void Fire(Combatant src, Combatant dst, Vector3 from, float power, Color color, float speed = 24f, float aoe = 0f, float size = 0.3f)
        {
            var p = Make(from, size, color);
            p.src = src; p.dst = dst; p.power = power; p.speed = speed; p.aoe = aoe;
            p.hits = dst.team;
        }

        // 지점으로 날아가 터지는 탄
        public static void FireAt(Combatant src, Team hits, Vector3 from, Vector3 point, float power, Color color, float speed, float aoe, float size = 0.45f)
        {
            var p = Make(from, size, color);
            p.src = src; p.toPoint = true; p.point = point; p.power = power; p.speed = speed; p.aoe = aoe; p.hits = hits;
        }

        void Update()
        {
            life -= Time.deltaTime;
            if (life <= 0f) { Destroy(gameObject); return; }

            Vector3 aim;
            if (toPoint) aim = point;
            else
            {
                if (dst == null || dst.IsDead || !dst.gameObject.activeInHierarchy) { Destroy(gameObject); return; }
                aim = dst.AimPoint;
            }
            transform.position = Vector3.MoveTowards(transform.position, aim, speed * Time.deltaTime);
            if ((transform.position - aim).sqrMagnitude > 0.2f) return;

            if (aoe > 0f)
            {
                Fx.Burst(aim, aoe, color);
                Combat.Area(src, aim, aoe, power, hits);
            }
            else if (!toPoint) Combat.Deal(src, dst, power);
            Destroy(gameObject);
        }
    }
}
