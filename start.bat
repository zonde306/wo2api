
REM ���API KEY������ð�Ƕ��ŷָ�
set API_KEYS=

REM �����õ�����
set AUTHORIZATION_TOKEN=

REM �˿ں�
set PORT=25100

python -m uvicorn app:app --port %PORT%
