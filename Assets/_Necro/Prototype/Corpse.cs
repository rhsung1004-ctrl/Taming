using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 쓰러진 적이 남기는 시체. 지배(E)하면 소환수가 되고, 시체 폭발(Q)의 재료도 된다.
    public class Corpse : MonoBehaviour
    {
        public static readonly List<Corpse> All = new List<Corpse>();

        public UnitDef def;
        float life;
        Transform wisp;

        public static void Create(Unit u)
        {
            var g = new GameObject("Corpse_" + u.def.id);
            g.layer = 2;
            g.transform.position = u.transform.position;
            g.transform.rotation = u.transform.rotation;
            var c = g.AddComponent<Corpse>();
            c.def = u.def;
            c.life = Db.CorpseTime(u.def.grade);
            var rig = Body.Build(u.def, false, g.transform);
            rig.LieDown();
            // 떠도는 영혼: 지배할 수 있다는 표시
            c.wisp = Util.Part(PrimitiveType.Sphere, g.transform, Vector3.up * (0.9f + 0.5f * u.def.size),
                               Vector3.one * (0.22f + 0.1f * u.def.size), Db.GradeColor(u.def.grade) * new Color(0.8f, 0.6f, 1f), default(Vector3), true);
        }

        void OnEnable() { All.Add(this); }
        void OnDisable() { All.Remove(this); }

        void Update()
        {
            life -= Time.deltaTime;
            if (wisp != null)
            {
                Vector3 p = wisp.localPosition;
                p.y = 0.9f + 0.5f * def.size + Mathf.Sin(Time.time * 3f + transform.position.x) * 0.15f;
                wisp.localPosition = p;
                if (life < 4f) wisp.gameObject.SetActive(Mathf.Sin(Time.time * 14f) > 0f);    // 곧 사라진다는 깜빡임
            }
            if (life <= 0f) Destroy(gameObject);
        }

        public void Consume() { Destroy(gameObject); }
    }
}
