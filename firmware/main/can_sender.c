#include <stdio.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_twai.h"
#include "esp_twai_onchip.h"
#include "can.h"

#define RX_GPIO CONFIG_CAN_TWAI_RX_GPIO
#define ESP_bitrate CAN_BITRATE
#define TX_GPIO CONFIG_CAN_TWAI_TX_GPIO
#define depth_count 5

void can_sender_run(void){// onchip, enable, then transmit
    twai_node_handle_t SENDER_NODE=NULL;
    twai_onchip_node_config_t node_config={
        .io_cfg={
            .tx=TX_GPIO,
            .rx=RX_GPIO,
        },
        .bit_timing={
            .bitrate=ESP_bitrate,
        },
        .tx_queue_depth=depth_count,
    };

    ESP_ERROR_CHECK(twai_new_node_onchip(&node_config, &SENDER_NODE));
    ESP_ERROR_CHECK(twai_node_enable(SENDER_NODE));

    while(1){
        uint8_t send_buff[8]={0,1,2,3,4,5,6,7};
        twai_frame_t send_frame={
            .header.id=0x1,
            .header.ide=false,
            .header.dlc=8,
            .buffer=send_buff,
            .buffer_len=sizeof(send_buff),
        };
        ESP_ERROR_CHECK(twai_node_transmit(SENDER_NODE,&send_frame,0));
        printf("Message sent\n");
        ESP_ERROR_CHECK(twai_node_transmit_wait_all_done(SENDER_NODE,-1));
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
