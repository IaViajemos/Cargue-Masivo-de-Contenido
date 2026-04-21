#!/usr/bin/env python3
"""Generar pruebas completas: 4 tipos LP x 2 marcas = 8 pruebas"""

import sys, json, logging
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, '.')
from lm_client import LMClient

def test_vjm(tipo_lp, ciudad, estado, estado_abrev, config):
    """Generar prueba completa VJM por tipo LP"""
    print(f'\n{tipo_lp.upper()} VJM: {ciudad}, {estado}')
    print('-' * 50)

    client = LMClient(brand='vjm')
    result = {
        'marca': 'VJM',
        'tipo_lp': tipo_lp,
        'ciudad': ciudad,
        'estado': estado,
        'bloques': {}
    }

    try:
        # B1
        print('  quicksearch... ', end='', flush=True)
        b1 = client.generate_vjm_quicksearch(ciudad, estado, estado_abrev=estado_abrev)
        print(f'OK ({len(b1.get("desc","").split())}p)')
        result['bloques']['quicksearch'] = {'desc_words': len(b1.get("desc","").split())}

        # B2
        print('  sectionCars... ', end='', flush=True)
        b2 = client.generate_vjm_sectioncars(ciudad, estado, estado_abrev=estado_abrev)
        print(f'OK ({len(b2.get("desc","").split())}p)')
        result['bloques']['sectionCars'] = {'desc_words': len(b2.get("desc","").split())}

        # B3
        print('  agencies... ', end='', flush=True)
        b3 = client.generate_vjm_agencies(ciudad, estado, estado_abrev=estado_abrev)
        print(f'OK ({len(b3.get("desc","").split())}p)')
        result['bloques']['agencies'] = {'desc_words': len(b3.get("desc","").split())}

        # B4
        print('  rentalCarFaqs... ', end='', flush=True)
        b4h = client.generate_vjm_rentalcarfaqs_header(ciudad, estado, estado_abrev=estado_abrev)
        b4q = client.generate_vjm_faq_questions(ciudad, estado, estado_abrev=estado_abrev)
        b4a = client.generate_vjm_faq_answers(ciudad, estado, estado_abrev=estado_abrev,
                                               precio_dia=config.get('precio_dia', '8'))
        print(f'OK ({len(b4h["desc"].split())}p)')
        result['bloques']['rentalCarFaqs'] = {'desc_words': len(b4h["desc"].split())}

        # B5
        print('  carRental... ', end='', flush=True)
        b5 = client.generate_vjm_carrental(ciudad, estado, estado_abrev=estado_abrev)
        print(f'OK ({len(b5.get("desc","").split())}p)')
        result['bloques']['carRental'] = {'desc_words': len(b5.get("desc","").split())}

        # B6
        print('  favoriteCities... ', end='', flush=True)
        locations = config.get('locations', [])
        b6 = client.generate_vjm_favoritecities(ciudad, estado, locations=locations)
        count_ok = sum(1 for i in range(1,7) if b6.get(f'desc_{i}','') and len(b6[f'desc_{i}'].split()) >= 15)
        print(f'OK ({len(b6.get("desc","").split())}p, {count_ok}/6 loc)')
        result['bloques']['favoriteCities'] = {'desc_words': len(b6.get("desc","").split()), 'locations_ok': count_ok}

        result['status'] = 'SUCCESS'
        return result

    except Exception as e:
        print(f'\nERROR: {e}')
        result['status'] = 'FAILED'
        result['error'] = str(e)
        return result


def test_mcr(tipo_lp, ciudad, estado, estado_abrev, config):
    """Generar prueba completa MCR por tipo LP"""
    print(f'\n{tipo_lp.upper()} MCR: {ciudad}, {estado}')
    print('-' * 50)

    client = LMClient(brand='mcr')
    result = {
        'marca': 'MCR',
        'tipo_lp': tipo_lp,
        'ciudad': ciudad,
        'estado': estado,
        'bloques': {}
    }

    try:
        # B1
        print('  quicksearch... ', end='', flush=True)
        b1 = client.generate_quicksearch(ciudad, estado)
        print(f'OK ({len(b1.get("desc","").split())}p)')
        result['bloques']['quicksearch'] = {'desc_words': len(b1.get("desc","").split())}

        # B2
        print('  fleet... ', end='', flush=True)
        b2 = client.generate_fleet(ciudad, estado)
        print(f'OK ({len(b2.get("desc","").split())}p)')
        result['bloques']['fleet'] = {'desc_words': len(b2.get("desc","").split())}

        # B3
        print('  reviews... ', end='', flush=True)
        b3 = client.generate_reviews(ciudad, estado)
        print(f'OK ({len(b3.get("desc","").split())}p)')
        result['bloques']['reviews'] = {'desc_words': len(b3.get("desc","").split())}

        # B4
        print('  rentcompanies... ', end='', flush=True)
        b4 = client.generate_rentcompanies(ciudad, estado)
        print(f'OK ({len(b4.get("desc","").split())}p)')
        result['bloques']['rentcompanies'] = {'desc_words': len(b4.get("desc","").split())}

        # B5
        print('  questions... ', end='', flush=True)
        b5 = client.generate_questions_header(ciudad, estado)
        print(f'OK ({len(b5.get("desc","").split())}p)')
        result['bloques']['questions'] = {'desc_words': len(b5.get("desc","").split())}

        # B6 - rentacar cambia por tipo_lp
        print('  rentacar... ', end='', flush=True)
        b6 = client.generate_rentacar(ciudad, estado, tipo_lp=tipo_lp)
        print(f'OK ({len(b6.get("desc","").split())}p)')
        result['bloques']['rentacar'] = {'desc_words': len(b6.get("desc","").split())}

        # B7 - fleetcarrusel / locationscarrusel
        print('  carrusel... ', end='', flush=True)
        if tipo_lp == 'ciudad':
            b7 = client.generate_fleetcarrusel(ciudad, estado)
            result['bloques']['fleetcarrusel'] = {'desc_words': len(b7.get("desc","").split())}
        else:
            b7 = client.generate_locationscarrusel(ciudad, estado, tipo_lp=tipo_lp)
            result['bloques']['locationscarrusel'] = {'desc_words': len(b7.get("desc","").split())}
        print(f'OK ({len(b7.get("desc","").split())}p)')

        result['status'] = 'SUCCESS'
        return result

    except Exception as e:
        print(f'\nERROR: {e}')
        result['status'] = 'FAILED'
        result['error'] = str(e)
        return result


if __name__ == '__main__':
    print('=' * 70)
    print('GENERANDO 8 PRUEBAS COMPLETAS (4 tipos LP x 2 marcas)')
    print('=' * 70)

    vjm_results = {}

    # 1. CIUDAD VJM
    vjm_results['ciudad'] = test_vjm('ciudad', 'Orlando', 'Florida', 'FL', {
        'precio_dia': '8',
        'locations': ['Aeropuerto Internacional de Orlando', 'Downtown Orlando', 'Puerto Cañaveral',
                      'Universal Studios', 'Disney', 'Kissimmee']
    })

    # 2. LOCALIDAD VJM
    vjm_results['localidad'] = test_vjm('localidad', 'Aeropuerto San Antonio', 'Texas', 'TX', {
        'precio_dia': '9',
        'locations': ['Sala de Espera', 'Terminal Principal', 'Estacionamiento', 'Hotel Cercano', 'Downtown', 'Carretera'],
        'localidad': 'Aeropuerto San Antonio'
    })

    # 3. AGENCIA VJM
    vjm_results['agencia'] = test_vjm('agencia', 'Dollar', 'USA', '', {
        'precio_dia': '7',
        'locations': [],
        'agencia': 'Dollar'
    })

    # 4. TIPO AUTO VJM
    vjm_results['tipo_auto'] = test_vjm('tipo_auto', 'Auto Economico', 'Orlando', 'FL', {
        'precio_dia': '6',
        'locations': [],
        'tipo_auto': 'Economico'
    })

    mcr_results = {}

    # 1. CIUDAD MCR
    mcr_results['ciudad'] = test_mcr('ciudad', 'Memphis', 'Tennessee', 'TN', {})

    # 2. LOCALIDAD MCR
    mcr_results['localidad'] = test_mcr('localidad', 'Aeropuerto San Antonio', 'Texas', 'TX', {})

    # 3. AGENCIA MCR
    mcr_results['agencia'] = test_mcr('agencia', 'Enterprise', 'Georgia', 'GA', {})

    # 4. TIPO AUTO MCR
    mcr_results['tipo_auto'] = test_mcr('tipo_auto', 'Convertibles', 'Florida', 'FL', {})

    # ============ RESUMEN FINAL ============
    print('\n' + '=' * 70)
    print('RESUMEN FINAL - 8 PRUEBAS GENERADAS')
    print('=' * 70)

    print('\nVJM:')
    for tipo, result in vjm_results.items():
        status = 'OK' if result['status'] == 'SUCCESS' else 'FAILED'
        print(f'  {tipo:12s}: {status}')

    print('\nMCR:')
    for tipo, result in mcr_results.items():
        status = 'OK' if result['status'] == 'SUCCESS' else 'FAILED'
        print(f'  {tipo:12s}: {status}')

    print('\nTodo completado exitosamente!')
