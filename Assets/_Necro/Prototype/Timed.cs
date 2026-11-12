using UnityEngine;

namespace Necro.Proto
{
    // 일정 간격으로 여러 번 실행하는 도우미 (창이 연달아 떨어지는 연출 등)
    public class Timed : MonoBehaviour
    {
        int left, index;
        float interval, t;
        System.Action<int> fn;

        public static void Run(int count, float interval, System.Action<int> fn, float delay = 0f)
        {
            var g = new GameObject("Timed");
            var c = g.AddComponent<Timed>();
            c.left = count;
            c.interval = interval;
            c.fn = fn;
            c.t = delay;
        }

        void Update()
        {
            t -= Time.deltaTime;
            while (t <= 0f && left > 0)
            {
                fn(index++);
                left--;
                t += Mathf.Max(0.001f, interval);
            }
            if (left <= 0) Destroy(gameObject);
        }
    }
}
