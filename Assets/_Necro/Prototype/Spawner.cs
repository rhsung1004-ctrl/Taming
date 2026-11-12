using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 적 무리. respawn이 0이면 다시 나오지 않는다.
    public class Spawner : MonoBehaviour
    {
        public string unitId;
        public float radius;
        public int count;
        public float respawn;
        public string group;
        readonly List<Unit> alive = new List<Unit>();
        float timer;

        public static Spawner Create(string id, Vector3 center, float radius, int count, float respawn, string group = null)
        {
            var g = new GameObject("Spawner_" + id);
            g.transform.position = center;
            var s = g.AddComponent<Spawner>();
            s.unitId = id;
            s.radius = radius;
            s.count = count;
            s.respawn = respawn;
            s.group = group;
            s.timer = respawn;
            for (int i = 0; i < count; i++) s.SpawnOne();
            return s;
        }

        void Update()
        {
            if (respawn <= 0f) return;
            if (alive.Count < count)
            {
                timer -= Time.deltaTime;
                if (timer <= 0f)
                {
                    SpawnOne();
                    timer = respawn;
                }
            }
            else timer = respawn;
        }

        void SpawnOne()
        {
            var d = Db.Get(unitId);
            for (int tries = 0; tries < 15; tries++)
            {
                Vector2 r = Random.insideUnitCircle * radius;
                Vector3 p = transform.position + new Vector3(r.x, 0f, r.y);
                p.y = World.GroundY(new Vector3(p.x, transform.position.y + 1f, p.z));
                if (p.y < 0.8f) continue;
                var u = Unit.Create(d, Team.Enemy, p);
                u.spawner = this;
                u.group = group;
                u.wander = Mathf.Clamp(radius * 0.5f, 2f, 9f);
                alive.Add(u);
                return;
            }
        }

        public void OnRemoved(Unit u) { alive.Remove(u); }
    }
}
