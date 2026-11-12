using UnityEngine;

namespace Necro
{
    public enum UnitGrade { Common, Elite, Hero, Boss }

    // 유닛 한 종의 데이터. Project 창 우클릭 → Create → Necro → Unit 으로 만든다.
    // 2D판(사령술사 키우기)의 data/units/*.tres 와 같은 항목을 쓴다. 적으로도, 지배한 소환수로도 같은 데이터를 쓴다.
    [CreateAssetMenu(menuName = "Necro/Unit", fileName = "Unit_")]
    public class UnitData : ScriptableObject
    {
        [Header("기본")]
        [Tooltip("2D판과 같은 id (예: skeleton, knight, lord)")] public string id;
        public string displayName;
        public UnitGrade grade;
        public GameObject modelPrefab;

        [Header("능력치")]
        public float maxHp = 40f;
        [Tooltip("소환수가 됐을 때 체력. 0이면 maxHp를 쓴다")] public float allyMaxHp;
        public float damage = 8f;
        [Tooltip("이동 속도 (m/s)")] public float moveSpeed = 4.5f;
        [Tooltip("근접은 닿는 거리, 원거리는 사거리 (m)")] public float attackRange = 1.8f;
        public float attackCooldown = 1f;

        [Header("원거리")]
        public bool ranged;
        public int projectileCount = 1;
        public float projectileSpeed = 20f;

        [Header("보상")]
        public int xpReward = 10;

        [Header("성장")]
        [Tooltip("소환수로 이 레벨에 도달하면 진화")] public int evolveLevel = 3;
        public UnitData evolvesTo;

        public float HpFor(bool ally) { return ally && allyMaxHp > 0f ? allyMaxHp : maxHp; }

        // 영혼 슬롯 비용 (2D판 balance.gd의 SLOT_COST와 동일)
        public int SlotCost
        {
            get
            {
                switch (grade)
                {
                    case UnitGrade.Elite: return 3;
                    case UnitGrade.Hero: return 4;
                    case UnitGrade.Boss: return 6;
                    default: return 1;
                }
            }
        }
    }
}
