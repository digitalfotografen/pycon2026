import matplotlib.pyplot as plt
from nordpool import elspot
AREAS = ["SE3"]
prices_spot = elspot.Prices()
prices = prices_spot.fetch(areas=AREAS,resolution=15)


se3 = prices["areas"]['SE3']
first = se3['values'][0]

prices = [(val['start'],val['value']) for val in se3['values']]
plt.step(*zip(*prices))
plt.ylabel('EUR/MWh')
plt.show()
