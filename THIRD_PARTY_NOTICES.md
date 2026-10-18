# Third-party components

The MIT license in this repository covers this project's own source only.
It does not relicense software downloaded or used through container images.

| Component | Use | Source and license authority |
| --- | --- | --- |
| Freqtrade | Official, pinned trading/backtesting image | https://github.com/freqtrade/freqtrade |
| FreqUI | Web UI bundled in the official Freqtrade image | https://github.com/freqtrade/frequi |
| Python | Optional gateway base image | https://www.python.org/psf/license/ |
| Redis | Optional upstream Redis 7.2 image | https://github.com/redis/redis/tree/7.2 |
| FastAPI, HTTPX, redis-py, Uvicorn, websockets | Gateway dependencies pinned in requirements.txt | Respective package distributions and upstream LICENSE files |
| NumPy, pandas, TA-Lib and other Freqtrade dependencies | Supplied by the upstream Freqtrade image | Respective upstream package licenses in that image |

No third-party trading strategy, pre-trained model, private dataset, personal
configuration, exchange credential or trading database is included in the
repository. StarterStrategy is an original demonstration, not a copied
community strategy.

The market gateway source is reused from the maintainer's original
ft_userdata working directory with their express confirmation of publication
rights and MIT licensing. Review upstream licenses and redistribution duties
again if modifying or redistributing upstream images or vendoring their code.
