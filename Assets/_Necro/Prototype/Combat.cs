using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    public enum Team { Player, Enemy }

    // 체력을 가진 모든 것(주인공, 소환수, 적)의 공통 부모
    public abstract class Combatant : MonoBehaviour
    {
        public static readonly List<Combatant> All = new List<Combatant>();

        public Team team;
        public float maxHp = 100f;
        public float hp = 100f;
        public float lastHurtTime = -99f;
        public float damageTakenMul = 1f;

        public bool IsDead { get { return hp <= 0f; } }
        public bool Alive { get { return hp > 0f && gameObject.activeInHierarchy; } }
        public abstract string DisplayName { get; }
        public virtual Vector3 AimPoint { get { return transform.position + Vector3.up; } }
        public virtual float Radius { get { return 0.5f; } }

        protected virtual void OnEnable() { All.Add(this); }
        protected virtual void OnDisable() { All.Remove(this); }

        public virtual void TakeDamage(float amount, Combatant src)
        {
            if (IsDead) return;
            hp = Mathf.Max(0f, hp - amount * damageTakenMul);
            lastHurtTime = Time.time;
            if (hp <= 0f) Die(src);
        }

        public void Heal(float amount)
        {
            if (IsDead) return;
            hp = Mathf.Min(maxHp, hp + amount);
        }

        protected abstract void Die(Combatant killer);
    }

    public static class Combat
    {
        static readonly List<Combatant> buffer = new List<Combatant>();

        public static void Deal(Combatant src, Combatant dst, float power)
        {
            if (dst == null || dst.IsDead) return;
            float dmg = power * Random.Range(0.9f, 1.1f);
            Vector3 at = dst.AimPoint + Vector3.up * 0.4f;
            bool playerInvolved = src is PlayerCtl || dst is PlayerCtl;
            dst.TakeDamage(dmg, src);
            // 군단끼리 치고받는 숫자까지 띄우면 화면이 지저분해져서, 주인공이 관련됐거나 큰 피해만 표시
            if (playerInvolved || dmg >= 40f)
                Hud.Popup(at, Mathf.RoundToInt(dmg).ToString(), dst.team == Team.Player ? new Color(1f, 0.45f, 0.45f) : Color.white, dmg >= 40f);
        }

        // 범위 피해: hits 팀에 속한 대상만 맞는다
        public static int Area(Combatant src, Vector3 pos, float radius, float power, Team hits)
        {
            buffer.Clear();
            foreach (var c in Combatant.All)
            {
                if (c.team != hits || c.IsDead) continue;
                float r = radius + c.Radius;
                if ((c.AimPoint - pos).sqrMagnitude <= r * r || (c.transform.position - pos).sqrMagnitude <= r * r) buffer.Add(c);
            }
            foreach (var c in buffer) Deal(src, c, power);
            return buffer.Count;
        }
    }
}
