package demo.fee;

/** 仓库主数据远程接口。 */
public interface WarehouseClient {

    /** 仓库是否已停用。 */
    boolean isClosed(String warehouseCode);
}
