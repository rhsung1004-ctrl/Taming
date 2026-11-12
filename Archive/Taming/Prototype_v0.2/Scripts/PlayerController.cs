using UnityEngine;

// 주인공(여성 테이머): 이동, 점프, 지팡이 공격, 탈것(지상/비행)
public class PlayerController : Combatant
{
    public CharacterController cc;
    public TamerRig rig;
    public PetData mount;
    public float stamina = 100f, maxStamina = 100f;
    public float CurrentSpeed;
    public Vector3 spawnPoint;

    GameObject mountObj;
    BodyRig mountRig;
    float vy, attackTimer, attackAnim, msgTime;
    Vector3 lastSafe;

    public bool Riding { get { return mount != null; } }
    public bool Flying { get { return mount != null && mount.Def.mount == MountType.Fly; } }
    public bool InAir { get { return Flying && !cc.isGrounded; } }
    public override string DisplayName { get { return "테이머"; } }
    public override Vector3 AimPoint { get { return transform.position + Vector3.up * (1.2f + rig.seat); } }

    public static PlayerController Create(Vector3 pos)
    {
        var g = new GameObject("Player");
        g.layer = 2;   // 지면 레이캐스트·카메라 충돌에서 제외
        g.transform.position = pos;
        var cc = g.AddComponent<CharacterController>();
        cc.height = 1.8f;
        cc.radius = 0.35f;
        cc.center = new Vector3(0f, 0.9f, 0f);
        cc.slopeLimit = 50f;
        cc.stepOffset = 0.4f;
        var p = g.AddComponent<PlayerController>();
        p.cc = cc;
        p.team = Team.Player;
        p.neutral = true;
        p.maxHp = 200f;
        p.hp = 200f;
        p.rig = Body.BuildTamer(g.transform);
        p.spawnPoint = pos;
        p.lastSafe = pos;
        return p;
    }

    void Update()
    {
        if (IsDead) return;
        float dt = Time.deltaTime;
        var hud = GameHUD.I;
        var gm = GameManager.I;
        attackTimer -= dt;
        attackAnim = Mathf.MoveTowards(attackAnim, 0f, dt * 4f);

        bool locked = gm.taming.active;
        Vector2 mv = locked ? Vector2.zero : hud.Move;
        Transform cam = gm.cam.transform;
        Vector3 fwd = Util.Flat(cam.forward).normalized;
        Vector3 right = Util.Flat(cam.right).normalized;
        Vector3 dir = fwd * mv.y + right * mv.x;
        float mag = Mathf.Clamp01(dir.magnitude);
        float speed = Riding ? mount.Def.rideSpeed : 6.5f;
        Vector3 horiz = mag > 0.01f ? dir.normalized * speed * mag : Vector3.zero;

        if (Flying) Fly(horiz, dt, locked);
        else Walk(horiz, dt, locked);

        if (mag > 0.05f)
            transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(dir), dt * 12f);

        CurrentSpeed = Util.Flat(cc.velocity).magnitude;
        rig.Animate(Mathf.Clamp01(CurrentSpeed / 6.5f), Riding, !cc.isGrounded && !Flying, attackAnim);
        if (mountRig != null)
            mountRig.Animate(Mathf.Clamp01(CurrentSpeed / Mathf.Max(1f, mount.Def.rideSpeed)), InAir, dt);

        if (Time.time - lastHurtTime > 4f) Heal(10f * dt);

        if (cc.isGrounded && transform.position.y > 0.6f) lastSafe = transform.position;
        if (!Flying && transform.position.y < -1.5f)
        {
            Teleport(lastSafe + Vector3.up);
            GameHUD.Toast("물에 빠졌어요! 안전한 곳으로 돌아왔어요.");
        }
    }

    void Walk(Vector3 horiz, float dt, bool locked)
    {
        if (cc.isGrounded)
        {
            vy = -2f;
            if (!locked && GameHUD.I.Down("jump")) vy = Riding ? 10.5f : 8.5f;
        }
        vy -= 25f * dt;
        cc.Move((horiz + Vector3.up * vy) * dt);
        stamina = Mathf.Min(maxStamina, stamina + 30f * dt);
    }

    void Fly(Vector3 horiz, float dt, bool locked)
    {
        var hud = GameHUD.I;
        float ceiling = GameDB.FlyCeiling(mount.Def.flyTier);
        bool up = !locked && hud.Held("jump");
        bool down = !locked && hud.Held("descend");
        float y = transform.position.y;

        if (up && stamina > 0f && y < ceiling)
        {
            vy = Mathf.MoveTowards(vy, 9f, 30f * dt);
            stamina -= 16f * dt;
        }
        else if (down) vy = Mathf.MoveTowards(vy, -13f, 40f * dt);
        else vy = Mathf.MoveTowards(vy, stamina > 0f ? -0.5f : -3.5f, 20f * dt);   // 활공

        if (y > ceiling)
        {
            vy = Mathf.Min(vy, -2.5f);
            if (up && Time.time > msgTime)
            {
                msgTime = Time.time + 4f;
                GameHUD.Toast(Util.EunNeun(mount.Def.name) + " 이보다 높이 날 수 없어요. 더 높은 하늘엔 상위 비행몹이 필요해요.", 4f);
            }
        }
        else if (up && stamina <= 0f && Time.time > msgTime)
        {
            msgTime = Time.time + 4f;
            GameHUD.Toast("스태미나가 부족해요. 땅에 내려 쉬면 회복돼요.");
        }

        if (!up) stamina = Mathf.Min(maxStamina, stamina + (cc.isGrounded ? 40f : 5f) * dt);
        stamina = Mathf.Max(0f, stamina);
        if (y < 0.6f && vy < 0f) vy = 0f;   // 바다 위에서는 수면 위를 유지
        cc.Move((horiz + Vector3.up * vy) * dt);
    }

    public void Attack(Combatant t)
    {
        if (attackTimer > 0f || t == null) return;
        attackTimer = 0.55f;
        attackAnim = 1f;
        rig.OnAttack();
        Projectile.Fire(this, t, rig.staffTip.position, 11f, null, new Color(0.6f, 0.9f, 1f));
    }

    public void Mount(PetData p)
    {
        if (p == null) return;
        if (p.reviveTimer > 0f)
        {
            GameHUD.Toast(Util.IGa(p.Def.name) + " 기절해 있어서 탈 수 없어요.");
            return;
        }
        if (Riding) Dismount(false);
        mount = p;
        var d = p.Def;
        bool fly = d.mount == MountType.Fly;
        float s = Mathf.Max(d.size, fly ? 1.7f : 1.35f);
        mountObj = new GameObject("Mount");
        mountObj.transform.SetParent(transform, false);
        mountRig = Body.Build(d, mountObj.transform, s);

        rig.seat = Body.SeatHeight(d.shape) * s - 0.78f;
        cc.height = 1.8f + rig.seat;
        cc.center = new Vector3(0f, cc.height * 0.5f, 0f);
        maxStamina = d.flyTier >= 2 ? 160f : 100f;
        stamina = maxStamina;

        if (p.instance != null) p.instance.gameObject.SetActive(false);   // 타고 있는 펫은 따라다니지 않음
        if (fly)
        {
            cc.Move(Vector3.up * 1.2f);
            vy = 4f;
        }
        GameHUD.Toast(Util.EulReul(d.name) + " 탔어요!" + (fly ? " [상승]을 꾹 눌러 날아오르세요." : ""), 4f);
    }

    public void Dismount(bool msg = true)
    {
        if (mount == null) return;
        var p = mount;
        mount = null;
        if (mountObj != null) Destroy(mountObj);
        mountObj = null;
        mountRig = null;
        rig.seat = 0f;
        cc.height = 1.8f;
        cc.center = new Vector3(0f, 0.9f, 0f);
        maxStamina = 100f;
        stamina = Mathf.Min(stamina, maxStamina);
        if (p.instance != null && p.inParty && p.reviveTimer <= 0f)
        {
            p.instance.gameObject.SetActive(true);
            p.instance.TeleportNear(this);
        }
        if (msg) GameHUD.Toast(p.Def.name + "에서 내렸어요.");
    }

    public void Teleport(Vector3 pos)
    {
        cc.enabled = false;
        transform.position = pos;
        cc.enabled = true;
        vy = 0f;
    }

    protected override void Die(Combatant killer)
    {
        GameHUD.Toast("쓰러졌어요... 계약 석상에서 다시 시작합니다.", 4f);
        Dismount(false);
        hp = maxHp;
        Teleport(spawnPoint);
        foreach (var p in GameState.pets)
            if (p.inParty && p.instance != null && p.instance.gameObject.activeSelf) p.instance.TeleportNear(this);
    }
}
