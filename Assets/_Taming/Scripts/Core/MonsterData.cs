using UnityEngine;

namespace Taming
{
    public enum Grade { Common, Uncommon, Rare, Epic, Legendary }
    public enum CombatRole { Tank, Melee, Ranged, Support }
    public enum MountKind { None, Ground, Fly, Swim }

    // 몬스터 한 종의 데이터. Project 창 우클릭 → Create → Taming → Monster 로 만든다.
    // 코드 수정 없이 이 에셋만 추가하면 새 몬스터가 생기는 구조 (2단계에서 본격 사용).
    [CreateAssetMenu(menuName = "Taming/Monster", fileName = "Monster_")]
    public class MonsterData : ScriptableObject
    {
        [Header("기본")]
        public string id;
        public string displayName;
        [TextArea] public string description;
        public Grade grade;
        public Element element;
        public CombatRole role;
        public GameObject modelPrefab;

        [Header("능력치 (Lv.1 기준)")]
        public float hp = 100f;
        public float attack = 10f;
        public float moveSpeed = 5f;
        public float attackRange = 2f;
        public float attackCooldown = 1.2f;
        [Tooltip("레벨당 능력치 증가율")] public float growthPerLevel = 0.12f;

        [Header("테이밍")]
        [Range(0f, 1f)] public float baseTameChance = 0.4f;
        public string favoriteFoodId;

        [Header("탈것")]
        public MountKind mount;
        [Tooltip("비행 단계 (1 = 깃털 새 ... 5 = 하늘 드래곤)")] public int flyTier;
        public float rideSpeed = 12f;

        public float HpAt(int level) { return hp * (1f + growthPerLevel * (level - 1)); }
        public float AttackAt(int level) { return attack * (1f + growthPerLevel * (level - 1)); }
    }
}
