package demo.fee;

import java.math.BigDecimal;

/** 提交存储费账单的入参。 */
public class BillSubmitCmd {

    private String warehouseCode;
    /** 账期，格式 yyyy-MM。 */
    private String period;
    private BigDecimal volumeCbm;
    private BigDecimal unitPrice;
    private int days;
    private int daysInMonth;

    public String getWarehouseCode() {
        return warehouseCode;
    }

    public void setWarehouseCode(String warehouseCode) {
        this.warehouseCode = warehouseCode;
    }

    public String getPeriod() {
        return period;
    }

    public void setPeriod(String period) {
        this.period = period;
    }

    public BigDecimal getVolumeCbm() {
        return volumeCbm;
    }

    public void setVolumeCbm(BigDecimal volumeCbm) {
        this.volumeCbm = volumeCbm;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public int getDays() {
        return days;
    }

    public void setDays(int days) {
        this.days = days;
    }

    public int getDaysInMonth() {
        return daysInMonth;
    }

    public void setDaysInMonth(int daysInMonth) {
        this.daysInMonth = daysInMonth;
    }
}
