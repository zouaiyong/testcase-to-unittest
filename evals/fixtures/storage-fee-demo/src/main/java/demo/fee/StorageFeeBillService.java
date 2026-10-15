package demo.fee;

import java.math.BigDecimal;

/**
 * 存储费账单的提交与审核规则。
 */
public class StorageFeeBillService {

    private final StorageFeeBillMapper billMapper;
    private final WarehouseClient warehouseClient;

    public StorageFeeBillService(StorageFeeBillMapper billMapper, WarehouseClient warehouseClient) {
        this.billMapper = billMapper;
        this.warehouseClient = warehouseClient;
    }

    /**
     * 提交账单。校验顺序：必填 → 仓库状态 → 重复账单。
     */
    public StorageFeeBill submit(BillSubmitCmd cmd) {
        if (cmd == null) {
            throw new BizException("提交参数不能为空");
        }
        if (cmd.getWarehouseCode() == null || cmd.getWarehouseCode().trim().isEmpty()) {
            throw new BizException("仓库编码不能为空");
        }
        if (cmd.getPeriod() == null || cmd.getPeriod().trim().isEmpty()) {
            throw new BizException("账期不能为空");
        }
        if (warehouseClient.isClosed(cmd.getWarehouseCode())) {
            throw new BizException("仓库已关闭，不可提交账单");
        }
        if (billMapper.existsByWarehouseAndPeriod(cmd.getWarehouseCode(), cmd.getPeriod())) {
            throw new BizException("该仓库本账期已存在账单，不可重复提交");
        }

        BigDecimal amount = StorageFeeCalculator.monthlyFee(
                cmd.getVolumeCbm(), cmd.getUnitPrice(), cmd.getDays(), cmd.getDaysInMonth());

        StorageFeeBill bill = new StorageFeeBill();
        bill.setWarehouseCode(cmd.getWarehouseCode());
        bill.setPeriod(cmd.getPeriod());
        bill.setAmount(amount);
        bill.setStatus(StorageFeeBill.STATUS_PENDING);
        billMapper.insert(bill);
        return bill;
    }

    /**
     * 审核账单。只有待审核状态可审核。
     */
    public void approve(Long id) {
        StorageFeeBill bill = billMapper.selectById(id);
        if (bill == null) {
            throw new BizException("账单不存在");
        }
        if (!StorageFeeBill.STATUS_PENDING.equals(bill.getStatus())) {
            throw new BizException("只有待审核账单可审核");
        }
        billMapper.updateStatus(id, StorageFeeBill.STATUS_APPROVED);
    }
}
