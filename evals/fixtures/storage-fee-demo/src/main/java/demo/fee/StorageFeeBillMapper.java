package demo.fee;

/** 账单持久层。真实项目里由 ORM 实现，这里只保留接口以便 mock。 */
public interface StorageFeeBillMapper {

    boolean existsByWarehouseAndPeriod(String warehouseCode, String period);

    int insert(StorageFeeBill bill);

    StorageFeeBill selectById(Long id);

    int updateStatus(Long id, String status);
}
