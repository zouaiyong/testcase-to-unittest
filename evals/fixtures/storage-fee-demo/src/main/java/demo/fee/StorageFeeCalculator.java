package demo.fee;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/**
 * 存储费口径计算。纯函数，不依赖任何协作方。
 */
public final class StorageFeeCalculator {

    private static final int SCALE = 2;

    /** 逾期日利率。财务口径尚未最终确认，先按万分之五。 */
    private static final BigDecimal OVERDUE_DAILY_RATE = new BigDecimal("0.0005");

    private StorageFeeCalculator() {
    }

    /**
     * 月存储费 = 体积 × 单价 × 在库天数 ÷ 当月天数，保留两位小数。
     */
    public static BigDecimal monthlyFee(BigDecimal volumeCbm, BigDecimal unitPrice, int days, int daysInMonth) {
        if (volumeCbm == null || unitPrice == null) {
            throw new IllegalArgumentException("体积与单价不能为空");
        }
        if (days < 0 || daysInMonth <= 0 || days > daysInMonth) {
            throw new IllegalArgumentException("在库天数必须在 0 到当月天数之间");
        }
        BigDecimal raw = volumeCbm.multiply(unitPrice)
                .multiply(BigDecimal.valueOf(days))
                .divide(BigDecimal.valueOf(daysInMonth), 10, RoundingMode.HALF_UP);
        return raw.setScale(SCALE, RoundingMode.DOWN);
    }

    /**
     * 按权重把总额拆到各项，每项保留两位小数；拆分产生的尾差并入最后一项，保证合计恒等于总额。
     */
    public static List<BigDecimal> allocateByWeight(BigDecimal total, List<BigDecimal> weights) {
        if (total == null || weights == null || weights.isEmpty()) {
            throw new IllegalArgumentException("总额与权重不能为空");
        }
        BigDecimal weightSum = BigDecimal.ZERO;
        for (BigDecimal w : weights) {
            weightSum = weightSum.add(w);
        }
        if (weightSum.signum() <= 0) {
            throw new IllegalArgumentException("权重合计必须大于 0");
        }
        List<BigDecimal> shares = new ArrayList<BigDecimal>(weights.size());
        BigDecimal allocated = BigDecimal.ZERO;
        for (int i = 0; i < weights.size(); i++) {
            BigDecimal share;
            if (i == weights.size() - 1) {
                share = total.subtract(allocated);
            } else {
                share = total.multiply(weights.get(i))
                        .divide(weightSum, 10, RoundingMode.HALF_UP)
                        .setScale(SCALE, RoundingMode.HALF_UP);
            }
            shares.add(share.setScale(SCALE, RoundingMode.HALF_UP));
            allocated = allocated.add(share);
        }
        return shares;
    }

    /**
     * 逾期滞纳金 = 账单金额 × 日利率 × 逾期天数，保留两位小数。
     */
    public static BigDecimal overdueFee(BigDecimal amount, int overdueDays) {
        if (amount == null || overdueDays < 0) {
            throw new IllegalArgumentException("账单金额不能为空，逾期天数不能为负");
        }
        return amount.multiply(OVERDUE_DAILY_RATE)
                .multiply(BigDecimal.valueOf(overdueDays))
                .setScale(SCALE, RoundingMode.HALF_UP);
    }
}
