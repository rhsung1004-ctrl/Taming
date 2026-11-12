using UnityEngine;

namespace Necro.Proto
{
    // 주인공(여성 사령술사): 이동·대시, 영혼 화살·뼈 창·시체 폭발·군단 강화, 본드래곤 탑승과 브레스
    public class PlayerCtl : Combatant
    {
        public CharacterController cc;
        public HeroRig rig;
        public float mana = 100f, maxMana = 100f;
        public int level = 1;
        public float xp;
        public Combatant focus;          // 지금 겨누고 있는 적
        public Unit mountUnit;
        public Vector3 spawnPoint;
        public float Speed;

        // HUD가 읽는 재사용 대기 (남은 시간 / 전체)
        public float spearCd, blastCd, buffCd, dashCd, legionCd, descentCd;
        public const float DashCdMax = 1.4f;

        // 기술 단계: 0 하급, 1 상급, 2 금주. 같은 칸의 기술이 단계에 따라 바뀐다 (Spells.cs)
        public int tier;
        public bool hasCrown;            // 왕관 조각을 되찾으면 왕관 스킬(망자의 군세)이 열린다

        GameObject mountObj;
        Rig mountRig;
        float mountScale = 1f;
        float vy, boltT, dashT, focusT, breathT, warnT;
        Vector3 dashDir, lastSafe;

        const int AimMask = ~(1 << 2);
        static readonly Color Soul = new Color(0.72f, 0.45f, 1f);

        public bool Riding { get { return mountUnit != null; } }
        public bool Grounded { get { return cc.isGrounded; } }
        public float XpNeed { get { return 30f + 25f * level; } }
        public override string DisplayName { get { return "사령술사"; } }
        public override Vector3 AimPoint { get { return transform.position + Vector3.up * (1.2f + rig.seat); } }
        public override float Radius { get { return Riding ? 2f : 0.5f; } }

        public static PlayerCtl Create(Vector3 pos)
        {
            var g = new GameObject("Player");
            g.layer = 2;
            g.transform.position = pos;
            var cc = g.AddComponent<CharacterController>();
            cc.height = 1.8f;
            cc.radius = 0.35f;
            cc.center = new Vector3(0f, 0.9f, 0f);
            cc.slopeLimit = 50f;
            cc.stepOffset = 0.4f;
            var p = g.AddComponent<PlayerCtl>();
            p.cc = cc;
            p.team = Team.Player;
            p.maxHp = 300f;
            p.hp = 300f;
            p.rig = Body.BuildHero(g.transform);
            p.spawnPoint = pos;
            p.lastSafe = pos;
            return p;
        }

        void Update()
        {
            if (IsDead || Game.I.paused) return;
            float dt = Time.deltaTime;
            boltT -= dt; spearCd -= dt; blastCd -= dt; buffCd -= dt; dashCd -= dt; breathT -= dt; warnT -= dt;
            legionCd -= dt; descentCd -= dt;

            Transform cam = Game.I.cam.transform;
            Vector3 fwd = Util.Flat(cam.forward).normalized;
            Vector3 right = Util.Flat(cam.right).normalized;
            Vector3 dir = fwd * In.Move.y + right * In.Move.x;
            float mag = Mathf.Clamp01(dir.magnitude);
            if (mag > 0.01f) dir /= dir.magnitude;

            if (Riding) Fly(dir * mag, dt);
            else Walk(dir, mag, dt);

            // 공격 중에는 겨누는 쪽을, 아니면 이동 방향을 본다
            Vector3 face = dir;
            if (In.AttackHeld) face = focus != null ? Util.Flat(focus.transform.position - transform.position) : fwd;
            if (face.sqrMagnitude > 0.01f)
                transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(face), dt * 12f);

            focusT -= dt;
            if (focusT <= 0f) { focusT = 0.1f; PickFocus(cam); }
            if (focus != null && !focus.Alive) focus = null;

            Skills(cam);

            mana = Mathf.Min(maxMana, mana + 6f * dt);
            if (Time.time - lastHurtTime > 5f) Heal(9f * dt);

            Speed = Util.Flat(cc.velocity).magnitude;
            rig.Animate(Mathf.Clamp01(Speed / 6.5f), Riding, !cc.isGrounded && !Riding, dt);
            if (mountRig != null) mountRig.Animate(Mathf.Clamp01(Speed / 9f), !cc.isGrounded, dt);

            if (cc.isGrounded && transform.position.y > 0.6f) lastSafe = transform.position;
            if (!Riding && transform.position.y < -1.5f)
            {
                Teleport(lastSafe + Vector3.up);
                Hud.Toast("물에 빠졌어요. 안전한 곳으로 돌아왔어요.");
            }
        }

        // ───────────── 이동 ─────────────
        void Walk(Vector3 dir, float mag, float dt)
        {
            if (In.DashDown && dashCd <= 0f)
            {
                dashCd = DashCdMax;
                dashT = 0.2f;
                dashDir = mag > 0.1f ? dir : transform.forward;
                Fx.Burst(AimPoint, 1.2f, new Color(0.4f, 0.25f, 0.7f), 0.25f);
            }
            Vector3 horiz = dir * mag * 6.5f;
            if (dashT > 0f)
            {
                dashT -= dt;
                horiz = dashDir * 24f;
            }
            if (cc.isGrounded)
            {
                vy = -2f;
                if (In.JumpDown) vy = 8.5f;
            }
            vy -= 25f * dt;
            cc.Move((horiz + Vector3.up * vy) * dt);
        }

        void Fly(Vector3 move, float dt)
        {
            const float ceiling = 110f;
            float y = transform.position.y;
            if (In.JumpHeld && y < ceiling) vy = Mathf.MoveTowards(vy, 11f, 34f * dt);
            else if (In.DescendHeld) vy = Mathf.MoveTowards(vy, -15f, 40f * dt);
            else vy = Mathf.MoveTowards(vy, cc.isGrounded ? -2f : -0.2f, 22f * dt);
            if (y > ceiling) vy = Mathf.Min(vy, -2f);
            if (y < 0.8f && vy < 0f) vy = 0f;          // 바다 위에서는 수면 위를 유지
            float speed = cc.isGrounded ? 10f : 24f;
            cc.Move((move * speed + Vector3.up * vy) * dt);
        }

        // ───────────── 조준 ─────────────
        void PickFocus(Transform cam)
        {
            Combatant best = null;
            float bestScore = float.MaxValue;
            float maxDist = Riding ? 90f : 40f, maxAng = Riding ? 12f : 16f;
            foreach (var u in Unit.Units)
            {
                if (u.team != Team.Enemy || !u.Alive) continue;
                Vector3 to = u.AimPoint - cam.position;
                float dist = to.magnitude;
                if (dist > maxDist) continue;
                float ang = Vector3.Angle(cam.forward, to);
                if (ang > maxAng) continue;
                float score = ang + dist * 0.05f;
                if (score < bestScore) { bestScore = score; best = u; }
            }
            if (best == null && !Riding)
            {
                // 화면 가운데에 적이 없으면 가까이 붙은 적을 겨눈다
                float bd = 13f * 13f;
                foreach (var u in Unit.Units)
                {
                    if (u.team != Team.Enemy || !u.Alive) continue;
                    float d = (u.transform.position - transform.position).sqrMagnitude;
                    if (d < bd) { bd = d; best = u; }
                }
            }
            focus = best;
        }

        // ───────────── 기술 ─────────────
        void Warn(string s)
        {
            if (warnT > 0f) return;
            warnT = 1.5f;
            Hud.Toast(s, 2f);
        }

        void Skills(Transform cam)
        {
            var game = Game.I;
            if (In.MountDown) ToggleMount();

            if (In.AttackHeld)
            {
                if (Riding) Breath(cam);
                else if (boltT <= 0f)
                {
                    rig.cast = 1f;
                    boltT = Spells.Basic(this, cam);
                }
            }

            if (In.SpearDown && !Riding && spearCd <= 0f)
            {
                if (tier == 0 && focus == null) Warn("뼈 창을 던질 적이 없어요.");
                else if (mana < Spells.SpearMana[tier]) Warn("마나가 부족해요.");
                else if (Spells.Spear(this, cam))
                {
                    mana -= Spells.SpearMana[tier];
                    spearCd = Spells.SpearCd[tier];
                    rig.cast = 1f;
                }
            }

            if (In.BlastDown && blastCd <= 0f)
            {
                if (mana < Spells.BlastMana[tier]) Warn("마나가 부족해요.");
                else if (Spells.Blast(this))
                {
                    mana -= Spells.BlastMana[tier];
                    blastCd = Spells.BlastCd[tier];
                    rig.cast = 1f;
                    if (tier == 2) Hud.Say("me", "다들, 한 번만 더 힘을 빌려줘.");
                }
                else Warn(tier == 2 ? "해일을 일으킬 시체나 적이 근처에 없어요." : "폭발시킬 시체가 근처에 없어요.");
            }

            if (In.BuffDown && buffCd <= 0f)
            {
                if (mana < Spells.BuffMana[tier]) Warn("마나가 부족해요.");
                else if (game.army.Buff(tier))
                {
                    mana -= Spells.BuffMana[tier];
                    buffCd = Spells.BuffCd[tier];
                    rig.cast = 1f;
                    if (tier == 0) Hud.Toast("군단 강화! 8초 동안 공격력 +30%, 체력 회복", 2.5f);
                    else if (tier == 1) Hud.Toast("광란! 10초 동안 공격 속도 폭증, 쓰러져도 잠시 더 싸워요", 2.5f);
                    else
                    {
                        Hud.Toast("불사의 군단! 8초 동안 군단이 쓰러지지 않아요", 2.5f);
                        Hud.Say("me", "아무도 쓰러지지 마. 내가 붙잡고 있을게.");
                        Hud.Flash(new Color(1f, 0.85f, 0.4f), 0.5f);
                        OrbitCam.Shake(0.5f);
                    }
                }
                else Warn("강화할 군단이 없어요.");
            }

            // 왕관 스킬: 망자의 군세
            if (In.CrownDown)
            {
                if (!hasCrown) Warn("왕관 조각을 되찾아야 쓸 수 있어요.");
                else if (legionCd > 0f) Warn("망자의 군세: " + Mathf.CeilToInt(legionCd) + "초 뒤에 다시 쓸 수 있어요.");
                else if (mana < Spells.LegionMana) Warn("마나가 부족해요.");
                else if (Spells.Legion(this))
                {
                    mana -= Spells.LegionMana;
                    legionCd = Spells.LegionCd;
                    rig.cast = 1f;
                    Hud.Say("me", "잠든 아이들아, 잠깐만 깨어 주렴. 다 같이 가자.");
                }
            }

            // 왕관 스킬: 강림 (타고 있지 않을 때 본드래곤을 불러 일직선 폭격)
            if (In.DescentDown)
            {
                var d = game.army.dragon;
                if (d == null) Warn("아직 본드래곤이 없어요.");
                else if (Riding) Warn("강림은 본드래곤에서 내려 있을 때 쓸 수 있어요.");
                else if (!d.gameObject.activeSelf || Strafe.Active) Warn("본드래곤이 지금은 올 수 없어요.");
                else if (descentCd > 0f) Warn("강림: " + Mathf.CeilToInt(descentCd) + "초 뒤에 다시 쓸 수 있어요.");
                else if (mana < Spells.DescentMana) Warn("마나가 부족해요.");
                else if (Spells.Descent(this, cam, d))
                {
                    mana -= Spells.DescentMana;
                    descentCd = Spells.DescentCd;
                    rig.cast = 1f;
                    Hud.Say("me", "내려오렴. 저 줄을 전부 쓸어 줘.");
                }
            }
        }

        void Breath(Transform cam)
        {
            if (breathT > 0f) return;
            if (mana < 1.5f) { Warn("마나가 부족해요. 잠시 기다리면 차올라요."); return; }
            breathT = 0.1f;
            mana -= 1.3f;
            Vector3 point;
            RaycastHit hit;
            if (focus != null) point = focus.transform.position + Vector3.up * 0.5f;
            else if (Physics.Raycast(cam.position, cam.forward, out hit, 160f, AimMask, QueryTriggerInteraction.Ignore)) point = hit.point;
            else point = cam.position + cam.forward * 80f;
            Vector2 r = Random.insideUnitCircle * 1.6f;
            point += new Vector3(r.x, 0f, r.y);
            Vector3 mouth = transform.position + transform.forward * 1.9f * mountScale + Vector3.up * 2f * mountScale;
            Projectile.FireAt(this, Team.Enemy, mouth, point, 20f + 3f * level, Soul, 60f, 3.2f, 0.6f);
        }

        // ───────────── 본드래곤 ─────────────
        void ToggleMount()
        {
            if (Riding) { Dismount(); return; }
            var d = Game.I.army.dragon;
            if (d == null) { Warn("아직 본드래곤이 없어요."); return; }
            if (Strafe.Active) { Warn("본드래곤이 강림 중이에요."); return; }
            if (!d.gameObject.activeSelf) { Warn("본드래곤이 다시 모이는 중이에요."); return; }
            Mount(d);
        }

        public void Mount(Unit d)
        {
            mountUnit = d;
            mountScale = d.def.size;
            mountObj = new GameObject("Mount");
            mountObj.transform.SetParent(transform, false);
            mountRig = Body.Build(d.def, true, mountObj.transform);
            rig.seat = Body.SeatHeight(d.def.shape) * mountScale - 0.78f;
            cc.height = 1.8f + rig.seat;
            cc.center = new Vector3(0f, cc.height * 0.5f, 0f);
            d.gameObject.SetActive(false);        // 타고 있는 동안에는 따로 돌아다니지 않는다
            cc.Move(Vector3.up * 1.5f);
            vy = 5f;
            Hud.Toast("본드래곤에 올랐어요! Space 상승 · Ctrl 하강 · 마우스 왼쪽 브레스", 5f);
        }

        public void Dismount()
        {
            if (mountUnit == null) return;
            var d = mountUnit;
            mountUnit = null;
            if (mountObj != null) Destroy(mountObj);
            mountObj = null;
            mountRig = null;
            rig.seat = 0f;
            cc.height = 1.8f;
            cc.center = new Vector3(0f, 0.9f, 0f);
            if (d != null && !d.IsDead)
            {
                d.gameObject.SetActive(true);
                d.TeleportNear(this);
            }
        }

        public void AddXp(float v)
        {
            xp += v;
            while (xp >= XpNeed)
            {
                xp -= XpNeed;
                level++;
                maxHp += 20f;
                hp = maxHp;
                Hud.Toast("레벨 업! Lv." + level + " — 영혼 슬롯 +1", 3f);
                Fx.Burst(AimPoint, 2.5f, new Color(1f, 0.85f, 0.4f), 0.5f);
            }
        }

        public void Teleport(Vector3 pos)
        {
            cc.enabled = false;
            transform.position = pos;
            cc.enabled = true;
            vy = 0f;
        }

        public override void TakeDamage(float amount, Combatant src)
        {
            if (dashT > 0f) return;      // 대시 중 무적
            base.TakeDamage(amount, src);
        }

        protected override void Die(Combatant killer)
        {
            Hud.Toast("쓰러졌어요… 봉인의 제단에서 다시 깨어납니다.", 4f);
            Dismount();
            hp = maxHp;
            mana = maxMana;
            Teleport(spawnPoint);
        }
    }
}
