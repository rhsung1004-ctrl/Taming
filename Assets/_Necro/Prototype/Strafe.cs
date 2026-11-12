using UnityEngine;

namespace Necro.Proto
{
    // 강림 연출: 본드래곤이 머리 위를 낮게 지나가며 브레스를 쏟는다
    public class Strafe : MonoBehaviour
    {
        const float Life = 2.3f, Length = 62f;

        PlayerCtl player;
        Unit dragon;
        Rig rig;
        Vector3 start, dir;
        float t, fireT;
        float size;

        public static bool Active;

        public static void Begin(PlayerCtl p, Unit dragon, Vector3 start, Vector3 dir)
        {
            var g = new GameObject("Strafe");
            g.layer = 2;
            var s = g.AddComponent<Strafe>();
            s.player = p;
            s.dragon = dragon;
            s.start = start;
            s.dir = dir;
            s.size = dragon.def.size;
            s.rig = Body.Build(dragon.def, true, g.transform);
            dragon.gameObject.SetActive(false);       // 폭격하는 동안에는 따로 돌아다니지 않는다
            Active = true;
            s.Place(0f);
        }

        void Place(float k)
        {
            float along = Mathf.Lerp(-28f, Length + 26f, k);
            float dip = 2f * k - 1f;
            Vector3 p = start + dir * along;
            p.y = start.y + 10f + 20f * dip * dip;
            transform.position = p;
            transform.rotation = Quaternion.LookRotation(dir + Vector3.up * (dip * 0.5f));
        }

        void Update()
        {
            float dt = Time.deltaTime;
            t += dt;
            float k = Mathf.Clamp01(t / Life);
            Place(k);
            rig.Animate(1f, true, dt);

            float along = Mathf.Lerp(-28f, Length + 26f, k);
            fireT -= dt;
            if (along > -6f && along < Length - 6f && fireT <= 0f)
            {
                fireT = 0.06f;
                Vector3 at = start + dir * (along + 7f);
                Vector2 r = Random.insideUnitCircle * 2.5f;
                at += new Vector3(r.x, 0f, r.y);
                at.y = World.GroundY(new Vector3(at.x, start.y + 1f, at.z)) + 0.3f;
                Vector3 mouth = transform.position + transform.forward * 1.9f * size + Vector3.up * 0.6f * size;
                Projectile.FireAt(player, Team.Enemy, mouth, at, 55f + 6f * player.level, new Color(0.72f, 0.45f, 1f), 80f, 4.5f, 0.7f);
                OrbitCam.Shake(0.4f);
            }
            if (t >= Life) Finish();
        }

        void Finish()
        {
            Active = false;
            if (dragon != null && !dragon.IsDead && player != null && player.mountUnit != dragon)
            {
                dragon.gameObject.SetActive(true);
                dragon.TeleportNear(player);
            }
            Destroy(gameObject);
        }

        void OnDestroy() { Active = false; }
    }
}
