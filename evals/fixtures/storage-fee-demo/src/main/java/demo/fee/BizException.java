package demo.fee;

/** 业务校验不通过时抛出，消息直接作为给用户的提示文案。 */
public class BizException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public BizException(String message) {
        super(message);
    }
}
