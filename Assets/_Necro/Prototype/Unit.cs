using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 적과 소환수 모두 이 컴포넌트 하나로 움직인다 (team으로 구분).
    // 군단이 수십 마리가 되어도 가볍도록 물리·내비게이션 없이 지형 높이만 따라간다.
    public class Unit : Combatant
    {
        public static readonly List<Unit> Units = new List<Unit>();

        public UnitDef def;
        public Spawner spawner;
        public string group;
        public Vector3 home;
        public float wander = 6f;
        public Combatant target;
        public float buffTimer;        // 군단 강화 남은 시간

        Rig rig;
        float atkTimer, aiTimer, specialTimer, windup, wanderTimer, burstTimer;
        int burstLeft;
        Vector3 wanderDest, sep, lastPos, burstPoint;
        bool hasWander, flyingNow, leashed;

        public bool Ally { get { return team == Team.Player; } }
        public override string DisplayName { get { return def.NameFor(Ally); } }
        public override Vector3 AimPoint { get { return transform.position + Vector3.up * Body.AimHeight(def.shape) * def.size; } }
        public override float Radius { get { return 0.45f * def.size; } }
        float Atk { get { return def.atk * (buffTimer > 0f ? 1.3f : 1f); } }

        public static Unit Create(UnitDef d, Team team, Vector3 pos)
        {
            var g = new GameObject(d.name);
            g.layer = 2;
            g.transform.position = pos;
            g.transform.rotation = Quaternion.Euler(0f, Random.Range(0f, 360f), 0f);
            var u = g.AddComponent<Unit>();
            u.def = d;
            u.team = team;
            u.maxHp = d.hp * (team == Team.Player ? 1.5f : 1f);    // 지배한 망자는 주인의 마력으로 더 단단해진다
            u.hp = u.maxHp;
            u.rig = Body.Build(d, team == Team.Player, g.transform);
            u.home = pos;
            u.lastPos = pos;
            u.aiTimer = Random.Range(0f, 0.3f);
            u.wanderTimer = Random.Range(1f, 5f);
            u.specialTimer = Random.Range(2f, 4f);
            return u;
        }

        public void PlayRise() { rig.rise = 0f; }

        protected override void OnEnable() { base.OnEnable(); Units.Add(this); }
        protected override void OnDisable() { base.OnDisable(); Units.Remove(this); }

        void Update()
        {
            if (def == null || IsDead) return;
            float dt = Time.deltaTime;
            atkTimer -= dt;
            specialTimer -= dt;
            buffTimer -= dt;

            aiTimer -= dt;
            if (aiTimer <= 0f)
            {
                aiTimer = 0.25f;
                Think();
            }

            if (windup > 0f) Windup(dt);
            else if (rig.rise >= 1f)
            {
                if (Ally) AllyMove(dt);
                else EnemyMove(dt);
            }
            Burst(dt);

            // 겹치지 않게 살짝 밀어내고 바닥에 붙인다
            Vector3 p = transform.position + sep * dt;
            float g = World.GroundY(p);
            if (g < 0.3f && !World.OnSky(p)) p = transform.position;     // 바다로 밀려나지 않게
            p.y = Mathf.MoveTowards(p.y, World.GroundY(p), 30f * dt);
            transform.position = p;

            float moved = Util.Flat(p - lastPos).magnitude / Mathf.Max(dt, 0.0001f);
            lastPos = p;
            rig.Animate(Mathf.Clamp01(moved / Mathf.Max(1f, def.speed)), flyingNow, dt);

            if (Time.time - lastHurtTime > 6f && target == null) Heal(maxHp * 0.06f * dt);
        }

        // ───────────── 판단 (0.25초마다) ─────────────
        void Think()
        {
            // 같은 편끼리 겹치지 않게 밀어내는 힘
            sep = Vector3.zero;
            foreach (var o in Units)
            {
                if (o == this || o.team != team) continue;
                Vector3 d = Util.Flat(transform.position - o.transform.position);
                float min = Radius + o.Radius + 0.25f;
                float m = d.magnitude;
                if (m < min && m > 0.001f) sep += d / m * (min - m) * 2.5f;
                else if (m <= 0.001f) sep += new Vector3(Random.Range(-1f, 1f), 0f, Random.Range(-1f, 1f));
            }
            sep = Vector3.ClampMagnitude(sep, 3f);

            if (target != null && (!target.Alive || !CanReach(target))) target = null;
            if (Ally) AllyThink();
            else EnemyThink();
        }

        bool CanReach(Combatant c)
        {
            float dy = c.transform.position.y - transform.position.y;
            if (def.ranged || def.shape == Shape.Dragon) return Mathf.Abs(dy) < 45f;
            return Mathf.Abs(dy) < 2.5f + def.size;
        }

        void EnemyThink()
        {
            float distHome = Util.Flat(transform.position - home).magnitude;
            if (distHome > 50f) leashed = true;                  // 너무 멀리 끌려왔으면 돌아간다
            else if (distHome < wander + 6f) leashed = false;
            if (leashed) { target = null; return; }
            if (target != null)
            {
                if (Vector3.Distance(target.transform.position, transform.position) > 42f) target = null;
                else return;
            }
            Combatant best = null;
            float bd = def.aggro * def.aggro;
            foreach (var c in All)
            {
                if (c.team != Team.Player || !c.Alive) continue;
                float d = (c.transform.position - transform.position).sqrMagnitude;
                if (d < bd && CanReach(c)) { bd = d; best = c; }
            }
            target = best;
        }

        void AllyThink()
        {
            var game = Game.I;
            var pl = game.player;
            if (game.army.mode == Army.Retreat) { target = null; return; }

            Vector3 pp = pl.transform.position;
            // 돌격: 주인공이 겨누는 적을 먼저 친다
            if (game.army.mode == Army.Charge && pl.focus != null && pl.focus.Alive && CanReach(pl.focus) &&
                (pl.focus.transform.position - pp).sqrMagnitude < 34f * 34f)
            {
                target = pl.focus;
                return;
            }
            if (target != null && (target.transform.position - pp).sqrMagnitude < 34f * 34f) return;

            float range = game.army.mode == Army.Charge ? 26f : 11f;
            Unit best = null;
            float bd = float.MaxValue;
            foreach (var u in Units)
            {
                if (u.team != Team.Enemy || !u.Alive || !CanReach(u)) continue;
                float dp = (u.transform.position - pp).sqrMagnitude;
                bool threat = u.target != null && dp < 22f * 22f;      // 우리를 공격 중인 적
                if (dp > range * range && !threat) continue;
                float d = (u.transform.position - transform.position).sqrMagnitude;
                if (d < bd) { bd = d; best = u; }
            }
            target = best;
        }

        // ───────────── 이동과 전투 ─────────────
        void EnemyMove(float dt)
        {
            if (target != null) { Fight(target, dt); return; }
            float distHome = Util.Flat(transform.position - home).magnitude;
            if (distHome > wander + 4f)
            {
                MoveTo(home, def.speed * (leashed ? 1.5f : 1f), 1f, dt);
                if (leashed) Heal(maxHp * 0.2f * dt);
                return;
            }
            wanderTimer -= dt;
            if (wanderTimer <= 0f)
            {
                wanderTimer = Random.Range(3f, 8f);
                Vector2 r = Random.insideUnitCircle * wander;
                wanderDest = home + new Vector3(r.x, 0f, r.y);
                hasWander = true;
            }
            if (hasWander) MoveTo(wanderDest, def.speed * 0.35f, 0.5f, dt);
        }

        void AllyMove(float dt)
        {
            var game = Game.I;
            var pl = game.player;
            Vector3 pp = pl.transform.position;
            float flat = Util.Flat(transform.position - pp).magnitude;
            float dy = Mathf.Abs(transform.position.y - pp.y);

            // 주인이 멀어졌거나 다른 높이의 땅에 내렸으면 그림자를 타고 따라온다
            if ((pl.Grounded && (flat > 45f || dy > 9f)) || flat > 75f)
            {
                if (TeleportNear(pl)) return;
            }

            if (target != null) { Fight(target, dt); return; }

            Vector3 dest = game.army.SlotPosition(this);
            float far = Util.Flat(dest - transform.position).magnitude;
            float sp = Mathf.Max(def.speed, pl.Speed * 1.05f) * (far > 7f ? 1.6f : 1f);
            MoveTo(dest, sp, 0.6f, dt);
            if (far < 1f) Face(pl.transform.forward, dt);
        }

        void Fight(Combatant t, float dt)
        {
            Vector3 tp = t.transform.position;
            float range = def.range + t.Radius;
            float dist = Vector3.Distance(transform.position, tp);
            bool flatIn = Util.Flat(tp - transform.position).magnitude <= range;
            bool inRange = def.ranged ? dist <= range : flatIn && Mathf.Abs(tp.y - transform.position.y) < 2.5f + def.size * 1.5f;

            if (def.shape == Shape.Keeper && specialTimer <= 0f && dist < 8f) { StartSlam(); return; }
            if (def.shape == Shape.Dragon && specialTimer <= 0f && dist < 32f) StartBreath(t);

            if (!inRange)
            {
                if (!flatIn || def.ranged) MoveTo(tp, def.speed * (Ally ? 1.15f : 1f), range * 0.85f, dt);
                else Face(tp - transform.position, dt);          // 머리 위를 나는 적은 올려다볼 뿐
                return;
            }
            Face(tp - transform.position, dt);
            if (atkTimer > 0f) return;
            atkTimer = def.cooldown;
            rig.Attack();
            if (def.ranged) Projectile.Fire(this, t, AimPoint + transform.forward * 0.4f, Atk, Ally ? new Color(0.72f, 0.45f, 1f) : new Color(1f, 0.85f, 0.6f));
            else Combat.Deal(this, t, Atk);
        }

        // 묘지기: 내려찍기 (바닥의 원이 다 퍼지면 범위 피해)
        void StartSlam()
        {
            windup = 1.1f;
            specialTimer = 6.5f;
            rig.Attack();
            Fx.Ring(transform.position, 6f, Ally ? new Color(0.72f, 0.45f, 1f) : new Color(1f, 0.3f, 0.2f), 1.1f);
        }

        void Windup(float dt)
        {
            windup -= dt;
            if (windup > 0f) return;
            rig.Attack();
            Fx.Burst(transform.position + Vector3.up * 0.5f, 6f, Ally ? new Color(0.72f, 0.45f, 1f) : new Color(1f, 0.4f, 0.2f));
            Combat.Area(this, transform.position, 6f, def.atk * 1.6f, Ally ? Team.Enemy : Team.Player);
        }

        // 고룡: 불덩이 다섯 발 (본드래곤이 되면 영혼 불꽃)
        void StartBreath(Combatant t)
        {
            specialTimer = 6f;
            burstLeft = 5;
            burstTimer = 0f;
            burstPoint = t.transform.position;
        }

        void Burst(float dt)
        {
            if (burstLeft <= 0) return;
            burstTimer -= dt;
            if (burstTimer > 0f) return;
            burstTimer = 0.22f;
            burstLeft--;
            if (target != null && target.Alive) burstPoint = target.transform.position;
            Vector2 r = Random.insideUnitCircle * 3.5f;
            Vector3 at = burstPoint + new Vector3(r.x, 0.3f, r.y);
            Vector3 mouth = transform.position + transform.forward * 1.7f * def.size + Vector3.up * 2f * def.size;
            Projectile.FireAt(this, Ally ? Team.Enemy : Team.Player, mouth, at, def.atk * 0.65f,
                              Ally ? new Color(0.72f, 0.45f, 1f) : new Color(1f, 0.5f, 0.15f), 26f, 3.5f, 0.7f);
        }

        void MoveTo(Vector3 dest, float speed, float stopDist, float dt)
        {
            Vector3 d = Util.Flat(dest - transform.position);
            float dist = d.magnitude;
            if (dist <= stopDist) return;
            Vector3 np = transform.position + d / dist * Mathf.Min(speed * dt, dist - stopDist);
            if (World.GroundY(np) < 0.3f && !World.OnSky(np)) return;     // 바다로 들어가지 않는다
            if (World.OnSky(transform.position) && !World.OnSky(new Vector3(np.x, transform.position.y, np.z))) return;   // 성채에서 떨어지지 않는다
            transform.position = np;
            Face(d, dt);
        }

        void Face(Vector3 dir, float dt)
        {
            dir.y = 0f;
            if (dir.sqrMagnitude < 0.0001f) return;
            transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(dir), dt * 10f);
        }

        public bool TeleportNear(PlayerCtl pl)
        {
            Vector3 pp = pl.transform.position;
            for (int i = 0; i < 6; i++)
            {
                Vector2 r = Random.insideUnitCircle * 5f;
                Vector3 p = new Vector3(pp.x + r.x, pp.y + 1f, pp.z + r.y) - pl.transform.forward * 3f;
                float g = World.GroundY(p);
                if (g < 0.3f) continue;                                  // 바다 위에서는 기다린다
                if (World.OnSky(pp) && !World.OnSky(p)) continue;        // 성채 위로 정확히 따라온다
                p.y = g;
                transform.position = p;
                lastPos = p;
                target = null;
                rig.rise = 0.3f;
                return true;
            }
            return false;
        }

        // ───────────── 피격과 죽음 ─────────────
        public override void TakeDamage(float amount, Combatant src)
        {
            if (IsDead) return;
            base.TakeDamage(amount, src);
            if (IsDead) return;
            if (!Ally && target == null && src != null && src.team == Team.Player && src.Alive && CanReach(src)) target = src;
        }

        protected override void Die(Combatant killer)
        {
            var game = Game.I;
            if (Ally)
            {
                Fx.Burst(AimPoint, 1.5f * def.size, new Color(0.5f, 0.3f, 0.8f));
                if (def.mount)
                {
                    // 본드래곤은 사라지지 않고 잠시 흩어졌다가 돌아온다
                    game.OnBoneDragonDown();
                    gameObject.SetActive(false);
                    return;
                }
                game.army.Remove(this);
                Destroy(gameObject);
                return;
            }
            game.OnEnemyKilled(this);
            if (spawner != null) spawner.OnRemoved(this);
            Corpse.Create(this);
            Destroy(gameObject);
        }

        public void Revive(PlayerCtl pl)
        {
            hp = maxHp;
            gameObject.SetActive(true);
            TeleportNear(pl);
        }
    }
}
