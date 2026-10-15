package demo.fee;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 基线：让阶段 0 的「基线条数」有一个非零起点。 */
class SmokeTest {

    @Test
    @DisplayName("冒烟：测试引擎能跑起来")
    void engineRuns() {
        assertEquals("待审核", StorageFeeBill.STATUS_PENDING);
    }
}
