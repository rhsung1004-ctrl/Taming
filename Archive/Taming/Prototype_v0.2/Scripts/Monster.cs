using System.Collections.Generic;
using UnityEngine;

// 야생 몬스터와 펫 모두 이 컴포넌트 하나로 동작한다 (team으로 구분)
public class Monster : Combatant
{
    public static readonly List<Monster> AllMonsters = new List<Monster>();

    public SpeciesDef def;
    public PetData pet;
    public int level = 1;
    public Spawner spawner;
    public Vector3 home;
    public float wanderRadius = 8f;
    public Combatant target;
    public float calmTimer;          // 0보다 크면 공격하지 않음 (먹이, 교감 중)
    public bool lockedByTaming;
    public bool fedFavorite;
    public bool everTameable;

    BodyRig rig;
    float atkTimer, skillTimer, wanderTimer, aggroCheck;
    Vector3 wanderDest;
    bool hasWander;
    Vector3 lastPos;
    bool flyingNow;

    const int GroundMask = ~(1 << 2);
    public const float SkillCooldown = 8f;

    public float Atk { get { return def.atk * (1f + 0.12f * (level - 1)); } }
    public float SkillReady01 { get { return 1f - Mathf.Clamp01(skillTimer / SkillCooldown); } }
    public bool Tameable { get { return team == Team.Wild && !IsDead && hp <= maxHp * 0.3f; } }
    public bool IsFlyer { get { return def.shape == BodyShape.Bird; } }
    public override string DisplayName { get { return def.name; } }
    public override Vector3 AimPoint
    {
        get { return transform.position + Vector3.up * (0.7f * def.size + (rig != null ? rig.root.localPosition.y : 0f)); }
    }

    public static Monster Create(SpeciesDef d, int level, Vector3 pos, PetData pet)
    {
        var g = new GameObject(d.name);
        g.transform.position = pos;
        var m = g.AddComponent<Monster>();
        m.Init(d, level, pet);
        return m;
    }

    void Init(SpeciesDef d, int lv, PetData p)
    {
        def = d;
        level = lv;
        pet = p;
        element = d.element;
        team = p != null ? Team.Player : Team.Wild;
        maxHp = d.hp * (1f + 0.12f * (lv - 1));
        hp = maxHp;
        rig = Body.Build(d, transform, d.size);
        home = transform.position;
        lastPos = transform.position;
        if (p != null) p.instance = this;
        wanderTimer = Random.Range(1f, 4f);
    }

    protected override void OnEnable() { base.OnEnable(); AllMonsters.Add(this); }
    protected override void OnDisable() { base.OnDisable(); AllMonsters.Remove(this); }

    void Update()
    {
        if (def == null || IsDead) return;
        float dt = Time.deltaTime;
        atkTimer -= dt;
        skillTimer -= dt;
        if (!lockedByTaming) calmTimer -= dt;

        if (team == Team.Wild) WildUpdate(dt);
        else PetUpdate(dt);

        float moved = (transform.position - lastPos).magnitude / Mathf.Max(dt, 0.0001f);
        lastPos = transform.position;
        rig.Animate(Mathf.Clamp01(moved / Mathf.Max(1f, def.moveSpeed)), flyingNow, dt);

        // 전투가 없으면 천천히 회복
        if (Time.time - lastHurtTime > 6f && target == null)
            Heal(maxHp * (team == Team.Player ? 0.04f : 0.08f) * dt);
    }

    // ───────────── 야생 AI ─────────────
    void WildUpdate(float dt)
    {
        var pl = GameManager.I.player;
        if (calmTimer > 0f)
        {
            Face(pl.transform.position - transform.position, dt);
            ApplyHeight(dt, IdleFlyY());
            return;
        }

        float distHome = Util.Flat(transform.position - home).magnitude;
        if (target != null && (target.IsDead || !target.gameObject.activeInHierarchy || distHome > 30f ||
            Vector3.Distance(target.transform.position, transform.position) > 26f || !CanReach(target)))
            target = null;

        if (target == null && def.aggressive)
        {
            aggroCheck -= dt;
            if (aggroCheck <= 0f)
            {
                aggroCheck = 0.4f;
                target = FindNearestPlayerSide(9f);
            }
        }

        if (target != null)
        {
            Fight(target, dt, Tameable ? 0.55f : 1f);
            return;
        }

        if (distHome > wanderRadius + 3f)
        {
            MoveTo(home, def.moveSpeed * 0.8f, 1f, dt);
        }
        else
        {
            wanderTimer -= dt;
            if (wanderTimer <= 0f)
            {
                wanderTimer = Random.Range(3f, 7f);
                Vector2 r = Random.insideUnitCircle * wanderRadius;
                wanderDest = home + new Vector3(r.x, 0f, r.y);
                hasWander = true;
            }
            if (hasWander) MoveTo(wanderDest, def.moveSpeed * 0.35f, 0.5f, dt);
        }
        ApplyHeight(dt, IdleFlyY());
    }

    float IdleFlyY()
    {
        if (!IsFlyer || def.id == "griffon") return float.NaN;
        return GroundY(transform.position) + 1.6f;
    }

    Combatant FindNearestPlayerSide(float radius)
    {
        Combatant best = null;
        float bd = radius * radius;
        foreach (var c in All)
        {
            if (c.team != Team.Player || c.IsDead) continue;
            float d = (c.transform.position - transform.position).sqrMagnitude;
            if (d < bd && CanReach(c))
            {
                bd = d;
                best = c;
            }
        }
        return best;
    }

    bool CanReach(Combatant c)
    {
        if (IsFlyer) return true;
        float dy = Mathf.Abs(c.transform.position.y - transform.position.y);
        if (def.ranged) return dy < def.attackRange;
        return dy < 3.5f;
    }

    // ───────────── 펫 AI ─────────────
    void PetUpdate(float dt)
    {
        var gm = GameManager.I;
        var pl = gm.player;
        Vector3 pp = pl.transform.position;
        float flatD = Util.Flat(transform.position - pp).magnitude;
        bool tooFar = IsFlyer ? Vector3.Distance(transform.position, pp) > 35f : flatD > 32f;
        if (tooFar || (!pl.InAir && Mathf.Abs(transform.position.y - pp.y) > 5f))
        {
            TeleportNear(pl);
            return;
        }

        Combatant enemy = ChooseEnemy(gm, pl);
        target = enemy;
        if (enemy != null)
        {
            Fight(enemy, dt, 1f);
            return;
        }

        int slot = gm.SlotOf(this);
        Vector3 dest = pp - pl.transform.forward * (2.2f + def.size) + pl.transform.right * ((slot - 1) * 1.9f);
        float far = Util.Flat(dest - transform.position).magnitude;
        float sp = Mathf.Max(def.moveSpeed, pl.CurrentSpeed * 1.1f) * (far > 6f ? 1.6f : 1f);
        MoveTo(dest, sp, 0.5f, dt);
        if (far < 0.8f) Face(pl.transform.forward, dt);
        ApplyHeight(dt, IsFlyer && pl.InAir ? pp.y + 0.4f : float.NaN);
    }

    Combatant ChooseEnemy(GameManager gm, PlayerController pl)
    {
        if (gm.mode == 2) return null;   // 후퇴
        Vector3 pp = pl.transform.position;
        Monster sel = gm.target;
        bool selValid = sel != null && !sel.IsDead && sel.team == Team.Wild &&
                        (sel.transform.position - pp).sqrMagnitude < 25f * 25f && CanReach(sel);

        // 선택한 대상이 테이밍 가능 상태면 펫은 공격을 멈춘다 (포획 대기)
        if (selValid && !sel.Tameable && (gm.mode == 1 || sel.target != null)) return sel;
        if (gm.mode == 1) return null;   // 집중 공격: 선택 대상만

        var cur = target as Monster;
        if (cur != null && !cur.IsDead && cur.team == Team.Wild && cur.target != null &&
            !(cur == sel && cur.Tameable) &&
            (cur.transform.position - pp).sqrMagnitude < 18f * 18f && CanReach(cur))
            return cur;

        Monster pick = null;
        float best = 15f * 15f;
        foreach (var m in AllMonsters)
        {
            if (m.team != Team.Wild || m.IsDead || m.target == null) continue;
            if (m == sel && m.Tameable) continue;
            float d = (m.transform.position - pp).sqrMagnitude;
            if (d < best && CanReach(m))
            {
                best = d;
                pick = m;
            }
        }
        return pick;
    }

    // ───────────── 공통 전투/이동 ─────────────
    void Fight(Combatant t, float dt, float speedMul)
    {
        Vector3 tp = t.transform.position;
        float range = def.attackRange + 0.4f * def.size;
        float dist = Vector3.Distance(transform.position, tp);
        if (dist > range)
        {
            MoveTo(tp, def.moveSpeed * speedMul * (team == Team.Player ? 1.15f : 1f), range * 0.85f, dt);
        }
        else
        {
            Face(tp - transform.position, dt);
            if (atkTimer <= 0f && calmTimer <= 0f) Attack(t, speedMul);
        }
        float flyY = float.NaN;
        if (IsFlyer)
        {
            float g = GroundY(transform.position);
            flyY = Mathf.Max(tp.y + 0.8f, team == Team.Wild && def.id != "griffon" ? g + 1.6f : g);
        }
        ApplyHeight(dt, flyY);
    }

    void Attack(Combatant t, float speedMul)
    {
        atkTimer = def.attackCooldown / Mathf.Max(0.3f, speedMul);
        if (def.ranged)
        {
            if (rig.anim != null) rig.anim.Attack();
            Projectile.Fire(this, t, AimPoint + transform.forward * 0.4f * def.size, Atk, element, GameDB.ElementColor(element));
        }
        else
        {
            rig.OnAttack();
            Combat.Deal(this, t, Atk, element);
        }
    }

    void MoveTo(Vector3 dest, float speed, float stopDist, float dt)
    {
        Vector3 d = Util.Flat(dest - transform.position);
        float dist = d.magnitude;
        if (dist <= stopDist) return;
        Vector3 np = transform.position + d / dist * Mathf.Min(speed * dt, dist - stopDist);
        if (!IsFlyer && GroundY(np) < 0.3f) return;   // 바다로 들어가지 않음
        transform.position = np;
        Face(d, dt);
    }

    void Face(Vector3 dir, float dt)
    {
        dir.y = 0f;
        if (dir.sqrMagnitude < 0.0001f) return;
        transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(dir), dt * 10f);
    }

    // flyAbsY: 날고 있을 때 목표 높이. NaN이면 땅에 붙는다.
    void ApplyHeight(float dt, float flyAbsY)
    {
        Vector3 p = transform.position;
        float g = GroundY(p);
        if (IsFlyer && !float.IsNaN(flyAbsY))
        {
            p.y = Mathf.Max(g, Mathf.Lerp(p.y, flyAbsY, dt * 3f));
            flyingNow = p.y > g + 0.3f;
        }
        else
        {
            if (p.y > g + 0.05f) p.y = Mathf.MoveTowards(p.y, g, (IsFlyer ? 8f : 25f) * dt);
            else p.y = g;
            flyingNow = IsFlyer && p.y > g + 0.3f;
        }
        transform.position = p;
    }

    float GroundY(Vector3 p)
    {
        RaycastHit hit;
        if (Physics.Raycast(new Vector3(p.x, p.y + 2.5f, p.z), Vector3.down, out hit, 200f, GroundMask, QueryTriggerInteraction.Ignore))
            return hit.point.y;
        return WorldBuilder.Height(p.x, p.z);
    }

    public void TeleportNear(PlayerController pl)
    {
        Vector3 pp = pl.transform.position;
        Vector3 p = pp - pl.transform.forward * 2.5f + pl.transform.right * Random.Range(-2f, 2f);
        p.y = (IsFlyer && pl.InAir) ? pp.y : WorldBuilder.GroundY(p.x, pp.y + 3f, p.z);
        transform.position = p;
        lastPos = p;
        target = null;
    }

    // ───────────── 피격/사망 ─────────────
    public override void TakeDamage(float amount, Combatant src)
    {
        if (IsDead) return;
        bool wasTameable = Tameable;
        base.TakeDamage(amount, src);
        if (IsDead || team != Team.Wild) return;
        if (!lockedByTaming) calmTimer = 0f;
        if (target == null && src != null && src.team == Team.Player) target = src;
        if (!wasTameable && Tameable && !everTameable)
        {
            everTameable = true;
            GameHUD.Popup(AimPoint + Vector3.up * 1.2f, "테이밍 가능!", new Color(1f, 0.85f, 0.3f), true);
            if (GameManager.I.target == this)
                GameHUD.Toast(Util.IGa(def.name) + " 지쳤어요! 펫들이 공격을 멈춥니다. [테이밍]을 누르세요.", 4.5f);
        }
    }

    protected override void Die(Combatant killer)
    {
        if (team == Team.Player)
        {
            GameHUD.Toast(Util.IGa(def.name) + " 기절했어요. 10초 뒤 회복됩니다.");
            if (pet != null) pet.reviveTimer = 10f;
            gameObject.SetActive(false);
            return;
        }
        GameManager.I.OnWildKilled(this, killer);
        if (spawner != null) spawner.OnRemoved(this);
        Destroy(gameObject);
    }

    public void Revive(PlayerController pl)
    {
        hp = maxHp * 0.6f;
        gameObject.SetActive(true);
        TeleportNear(pl);
    }

    public void BecomePet(PetData p)
    {
        pet = p;
        p.instance = this;
        team = Team.Player;
        target = null;
        calmTimer = 0f;
        lockedByTaming = false;
        everTameable = false;
        fedFavorite = false;
        spawner = null;
        hp = Mathf.Max(hp, maxHp * 0.5f);
        GameHUD.Popup(AimPoint + Vector3.up, "♥ 동료가 되었다!", new Color(1f, 0.55f, 0.75f), true);
    }

    public void GainExp(float e)
    {
        if (pet == null) return;
        pet.exp += e;
        while (pet.exp >= pet.ExpToNext)
        {
            pet.exp -= pet.ExpToNext;
            pet.level++;
        }
        if (pet.level != level)
        {
            float ratio = hp / maxHp;
            level = pet.level;
            maxHp = def.hp * (1f + 0.12f * (level - 1));
            hp = Mathf.Min(maxHp, maxHp * ratio + maxHp * 0.2f);
            GameHUD.Popup(AimPoint + Vector3.up, "레벨 업! Lv." + level, new Color(1f, 0.85f, 0.3f), true);
        }
    }

    // ───────────── 펫 스킬 ─────────────
    public bool UseSkill(Combatant tgt)
    {
        if (IsDead || !gameObject.activeInHierarchy || skillTimer > 0f) return false;
        if (tgt == null || tgt.IsDead || tgt.team != Team.Wild)
            tgt = (target != null && !target.IsDead) ? target : null;

        switch (def.role)
        {
            case Role.Tank:
                foreach (var m in AllMonsters)
                {
                    if (m.team != Team.Wild || m.IsDead || m.lockedByTaming) continue;
                    if ((m.transform.position - transform.position).sqrMagnitude < 144f) m.target = this;
                }
                Heal(maxHp * 0.3f);
                GameHUD.Popup(AimPoint + Vector3.up, "도발!", new Color(0.5f, 1f, 0.5f), true);
                break;

            case Role.Support:
                foreach (var c in All)
                    if (c.team == Team.Player && !c.IsDead) c.Heal(c.maxHp * 0.25f);
                GameHUD.Popup(AimPoint + Vector3.up, "치유!", new Color(0.5f, 1f, 0.6f), true);
                break;

            default:
                if (tgt == null || (tgt.transform.position - transform.position).sqrMagnitude > 20f * 20f)
                {
                    GameHUD.Toast("스킬을 쓸 대상이 없어요. 몬스터를 터치해 선택하세요.");
                    return false;
                }
                if (def.role == Role.Melee)
                {
                    Vector3 dir = Util.Flat(tgt.transform.position - transform.position);
                    if (dir.magnitude > 2f)
                    {
                        Vector3 np = tgt.transform.position - dir.normalized * 1.5f;
                        transform.position = np;
                        lastPos = np;
                    }
                    Face(dir, 1f);
                    rig.OnAttack();
                    Combat.Deal(this, tgt, Atk * 2.5f, element);
                    GameHUD.Popup(AimPoint + Vector3.up, "강타!", new Color(1f, 0.7f, 0.3f), true);
                }
                else
                {
                    for (int i = 0; i < 3; i++)
                        Projectile.Fire(this, tgt, AimPoint + Random.insideUnitSphere * 0.4f, Atk * 1.1f, element, GameDB.ElementColor(element));
                    GameHUD.Popup(AimPoint + Vector3.up, "연사!", new Color(0.6f, 0.9f, 1f), true);
                }
                break;
        }
        skillTimer = SkillCooldown;
        return true;
    }
}
